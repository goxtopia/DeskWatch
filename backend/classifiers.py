import os
import base64
import json
import re
import httpx
from PIL import Image

import torch
import torch.nn as nn

# MLP classifier head definition
class CLIPMLPClassifier(nn.Module):
    def __init__(self, input_dim=512, hidden_dim=128, num_classes=5):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, num_classes)
        )
    def forward(self, x):
        return self.net(x)

# Linear classifier head definition
class CLIPLinearClassifier(nn.Module):
    def __init__(self, input_dim=512, num_classes=5):
        super().__init__()
        self.linear = nn.Linear(input_dim, num_classes)
    def forward(self, x):
        return self.linear(x)

# Global variables for caching loaded models to save memory and initialization time
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_cnn_model = None
_cnn_labels = None
_mlp_model = None
_mlp_labels = None

def get_clip_prompts(label):
    label_lower = label.lower()
    
    # Special treatment for "Away" / Vacant categories
    if any(x in label_lower for x in ["away", "absent", "vacant", "nobody", "empty"]):
        return [
            "a photo of an empty office desk with no one sitting there.",
            "a webcam view of a vacant chair at a computer desk.",
            "an empty workspace with nobody sitting in the office chair.",
            "a surveillance photo of a vacant computer desk."
        ]
        
    # Standard prefix/postfix mapping for common activities
    if any(x in label_lower for x in ["computer", "laptop", "working", "pc"]):
        action = "typing and working on a computer at a desk"
    elif any(x in label_lower for x in ["phone", "mobile", "smartphone", "screen"]):
        action = "looking at a mobile phone screen at a desk"
    elif any(x in label_lower for x in ["eat", "food", "snack", "meal"]):
        action = "eating food or snacks at their desk"
    elif any(x in label_lower for x in ["drink", "water", "coffee", "tea", "cup", "beverage"]):
        action = "drinking a beverage from a cup at their desk"
    else:
        # Fallback for other configured behaviors
        action = label_lower
        
    return [
        f"a photo of a person {action}.",
        f"a webcam photo of a person {action}.",
        f"a photo of a person sitting at their desk and {action}."
    ]

def classify_with_clip(image_path, categories, model_name):
    global _clip_model, _clip_preprocess, _clip_tokenizer
    
    # Lazy imports to save startup speed
    import torch
    import open_clip
    from timm.utils import reparameterize_model

    if _clip_model is None or _clip_preprocess is None or _clip_tokenizer is None:
        print(f"Loading Open CLIP model: {model_name}...")
        m_name = 'MobileCLIP2-S0'
        pretrained = 'dfndr2b'
        
        # If model_name is set to custom open_clip format, try to parse it
        if model_name != "MobileCLIP2-S0" and "/" in model_name:
            try:
                parts = model_name.split("/")
                m_name = parts[0]
                pretrained = parts[1]
            except Exception:
                pass
                
        model, _, preprocess = open_clip.create_model_and_transforms(m_name, pretrained=pretrained)
        model.eval()
        
        # Reparameterize model for better performance
        try:
            model = reparameterize_model(model)
        except Exception as e:
            print(f"Failed to reparameterize model: {e}")
            
        _clip_model = model
        _clip_preprocess = preprocess
        _clip_tokenizer = open_clip.get_tokenizer(m_name)
        print("Open CLIP model loaded successfully.")

    # Load and preprocess image
    image = Image.open(image_path).convert("RGB")
    image_input = _clip_preprocess(image).unsqueeze(0)
    
    # Prepare text prompts using ensembling
    all_prompts = []
    category_slices = []
    
    for cat in categories:
        cat_prompts = get_clip_prompts(cat)
        start_idx = len(all_prompts)
        all_prompts.extend(cat_prompts)
        end_idx = len(all_prompts)
        category_slices.append((start_idx, end_idx))
        
    text_input = _clip_tokenizer(all_prompts)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _clip_model = _clip_model.to(device)
    image_input = image_input.to(device)
    text_input = text_input.to(device)
    
    # Determine autocast context
    if device.type == "cuda":
        autocast_ctx = torch.amp.autocast("cuda")
    else:
        import contextlib
        autocast_ctx = contextlib.nullcontext()
        
    with torch.no_grad(), autocast_ctx:
        image_features = _clip_model.encode_image(image_input)
        text_features = _clip_model.encode_text(text_input)
        
        # Normalize features
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        
        # Mean pooling (ensemble) text features per category
        ensembled_text_features = []
        for start, end in category_slices:
            cat_feats = text_features[start:end]  # shape: (M, D)
            mean_feat = cat_feats.mean(dim=0, keepdim=True)  # shape: (1, D)
            mean_feat /= mean_feat.norm(dim=-1, keepdim=True)  # re-normalize
            ensembled_text_features.append(mean_feat)
            
        # Stack all ensembled category vectors: shape (C, D)
        stacked_text_features = torch.cat(ensembled_text_features, dim=0)
        
        # Calculate probabilities
        similarity = (100.0 * image_features @ stacked_text_features.T)
        probs = similarity.softmax(dim=-1).cpu().numpy()[0]
        
    best_idx = probs.argmax()
    predicted_label = categories[best_idx]
    confidence = float(probs[best_idx])
    
    return predicted_label, confidence

def classify_with_vlm(image_path, categories, api_url, api_key, model_name, prompt_template):
    # Load and encode image
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        
    # Render categories in prompt
    categories_str = ", ".join([f"'{c}'" for c in categories])
    prompt = prompt_template.format(categories=categories_str)
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "response_format": {"type": "json_object"}
    }
    
    try:
        # Timeout after 20 seconds
        with httpx.Client(timeout=20.0) as client:
            response = client.post(api_url + "/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            res_data = response.json()
            
        content = res_data["choices"][0]["message"]["content"]
        
        # Parse the JSON response
        data = json.loads(content)
        label = data.get("label")
        confidence = data.get("confidence", 1.0)
        
        # Verify the label is one of categories, find closest match if not exact
        if label in categories:
            return label, float(confidence)
            
        # Fallback fuzzy match
        for cat in categories:
            if cat.lower() == label.lower():
                return cat, float(confidence)
                
        # If still not found, check if response contains any category substring
        for cat in categories:
            if cat.lower() in label.lower():
                return cat, float(confidence)
                
        # Default fallback
        return categories[0], 0.5
        
    except Exception as e:
        print(f"Error classifying with VLM: {e}")
        # Try parsing markdown json if VLM returned raw text with json codeblock
        try:
            # Maybe the API failed because response_format wasn't supported, let's retry without it
            payload.pop("response_format", None)
            with httpx.Client(timeout=20.0) as client:
                response = client.post(api_url + "/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                res_data = response.json()
            content = res_data["choices"][0]["message"]["content"]
            
            # Extract JSON block using regex
            match = re.search(r"\{.*?\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                label = data.get("label")
                confidence = data.get("confidence", 0.8)
                for cat in categories:
                    if cat.lower() == label.lower():
                        return cat, float(confidence)
        except Exception as e2:
            print(f"Fallback VLM parsing failed: {e2}")
            
        # Final fallback
        return categories[0], 0.0

def get_cnn_classifier():
    global _cnn_model, _cnn_labels
    
    import torch
    import torchvision.models as models
    import torch.nn as nn
    
    model_path = os.path.join("models", "cnn_classifier.pth")
    labels_path = os.path.join("models", "cnn_labels.json")
    
    if not os.path.exists(model_path) or not os.path.exists(labels_path):
        raise FileNotFoundError("CNN model or labels file not found. Please train the model first.")
        
    with open(labels_path, "r", encoding="utf-8") as f:
        _cnn_labels = json.load(f)
        
    # Recreate the model architecture
    # By default, we use convnext_tiny
    num_classes = len(_cnn_labels)
    
    # We load weights=None since we are loading custom weights
    model = models.convnext_tiny(weights=None)
    # Modify head
    in_features = model.classifier[2].in_features
    model.classifier[2] = nn.Linear(in_features, num_classes)
    
    # Load state dict
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    
    _cnn_model = model
    return _cnn_model, _cnn_labels

def classify_with_cnn(image_path, categories):
    import torch
    from torchvision import transforms
    
    model, label_mapping = get_cnn_classifier()
    
    # Find active labels from configuration and map indices
    # Note: Since the configuration categories can change, we need to map the predicted label index back to config category
    # If the CNN labels mismatch current configuration, we map by name matching
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Preprocess image
    image = Image.open(image_path).convert("RGB")
    preprocess = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    
    input_tensor = preprocess(image).unsqueeze(0).to(device)
    
    with torch.no_grad():
        outputs = model(input_tensor)
        probs = torch.softmax(outputs, dim=1).cpu().numpy()[0]
        
    best_idx = probs.argmax()
    predicted_label = label_mapping[best_idx]
    confidence = float(probs[best_idx])
    
    # Ensure predicted label is one of the currently configured categories
    # (If categories changed since last training)
    if predicted_label in categories:
        return predicted_label, confidence
        
    # Match by name if possible
    for cat in categories:
        if cat.lower() == predicted_label.lower():
            return cat, confidence
            
    # Fallback to whatever matches, or first config category
    return categories[0], 0.0

def get_clip_features(image_path):
    global _clip_model, _clip_preprocess
    
    import open_clip
    from timm.utils import reparameterize_model
    
    if _clip_model is None or _clip_preprocess is None:
        print("Loading Open CLIP model for feature extraction...")
        model, _, preprocess = open_clip.create_model_and_transforms('MobileCLIP2-S0', pretrained='dfndr2b')
        model.eval()
        try:
            model = reparameterize_model(model)
        except Exception as e:
            print(f"Failed to reparameterize CLIP model: {e}")
        _clip_model = model
        _clip_preprocess = preprocess
        
    image = Image.open(image_path).convert("RGB")
    image_input = _clip_preprocess(image).unsqueeze(0)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _clip_model = _clip_model.to(device)
    image_input = image_input.to(device)
    
    if device.type == "cuda":
        autocast_ctx = torch.amp.autocast("cuda")
    else:
        import contextlib
        autocast_ctx = contextlib.nullcontext()
        
    with torch.no_grad(), autocast_ctx:
        image_features = _clip_model.encode_image(image_input)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        image_features = image_features.float()
        
    return image_features

def get_mlp_classifier():
    global _mlp_model, _mlp_labels
    
    model_path = os.path.join("models", "clip_mlp_classifier.pth")
    labels_path = os.path.join("models", "clip_mlp_labels.json")
    
    if not os.path.exists(model_path) or not os.path.exists(labels_path):
        raise FileNotFoundError("CLIP classifier model or labels file not found. Please train the model first.")
        
    with open(labels_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if isinstance(data, list):
        categories = data
        model_type = "mlp"
    else:
        categories = data.get("categories", [])
        model_type = data.get("model_type", "mlp")
        
    _mlp_labels = categories
    num_classes = len(categories)
    
    if model_type == "linear":
        model = CLIPLinearClassifier(input_dim=512, num_classes=num_classes)
    else:
        model = CLIPMLPClassifier(input_dim=512, hidden_dim=128, num_classes=num_classes)
        
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    
    _mlp_model = model
    return _mlp_model, _mlp_labels

def classify_with_clip_mlp(image_path, categories):
    model, label_mapping = get_mlp_classifier()
    
    # Extract CLIP image features
    features = get_clip_features(image_path)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    features = features.to(device).float()
    
    with torch.no_grad():
        outputs = model(features)
        probs = torch.softmax(outputs, dim=1).cpu().numpy()[0]
        
    best_idx = probs.argmax()
    predicted_label = label_mapping[best_idx]
    confidence = float(probs[best_idx])
    
    if predicted_label in categories:
        return predicted_label, confidence
        
    for cat in categories:
        if cat.lower() == predicted_label.lower():
            return cat, confidence
            
    return categories[0], 0.0

def classify_image(image_path, config):
    active_model = config.get("active_model", "clip")
    categories = config.get("categories", [])
    
    if not categories:
        raise ValueError("No categories configured for classification.")
        
    if active_model == "clip":
        model_name = config.get("clip_model_name", "openai/clip-vit-base-patch32")
        return classify_with_clip(image_path, categories, model_name)
    elif active_model == "vlm":
        api_url = config.get("vlm_api_url", "https://api.openai.com/v1")
        api_key = config.get("vlm_api_key", "")
        model_name = config.get("vlm_model", "gpt-4o-mini")
        prompt_template = config.get("vlm_prompt", "")
        return classify_with_vlm(image_path, categories, api_url, api_key, model_name, prompt_template)
    elif active_model == "cnn":
        return classify_with_cnn(image_path, categories)
    elif active_model == "clip_mlp":
        return classify_with_clip_mlp(image_path, categories)
    else:
        raise ValueError(f"Unknown classification model: {active_model}")
