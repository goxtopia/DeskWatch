import os
import json
import glob
import threading
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from backend.db import get_safe_dir_name

# Global training status
_train_lock = threading.Lock()
_train_status = {
    "is_training": False,
    "current_epoch": 0,
    "total_epochs": 0,
    "train_loss": 0.0,
    "val_loss": 0.0,
    "val_accuracy": 0.0,
    "status_message": "Idle",
    "error": None,
    "logs": []
}

def get_training_status():
    with _train_lock:
        # copy dict, but make a copy of logs list as well to avoid mutation
        status_copy = _train_status.copy()
        status_copy["logs"] = list(_train_status["logs"])
        return status_copy

def update_training_status(**kwargs):
    with _train_lock:
        for k, v in kwargs.items():
            if k in _train_status:
                _train_status[k] = v
                if k == "status_message":
                    print(v)
                    if not _train_status["logs"] or _train_status["logs"][-1] != v:
                        _train_status["logs"].append(v)

def add_training_log(message: str):
    print(message)
    with _train_lock:
        _train_status["logs"].append(message)

class DeskwatchDataset(Dataset):
    def __init__(self, image_paths, labels, label_to_idx, transform=None):
        self.image_paths = image_paths
        self.labels = labels
        self.label_to_idx = label_to_idx
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        label = self.labels[idx]
        class_idx = self.label_to_idx[label]
        
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            # Fallback if image is corrupted: return black image
            image = Image.new("RGB", (224, 224))
            print(f"Error loading image {img_path}: {e}")
            
        if self.transform:
            image = self.transform(image)
            
        return image, class_idx

class MLPDataset(Dataset):
    def __init__(self, features, targets):
        self.features = features
        self.targets = targets

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx], self.targets[idx]

def start_training_in_background(epochs=5, batch_size=8, lr=1e-4, train_type="cnn"):
    status = get_training_status()
    if status["is_training"]:
        return False, "Training is already in progress."
        
    update_training_status(
        is_training=True,
        current_epoch=0,
        total_epochs=epochs,
        train_loss=0.0,
        val_loss=0.0,
        val_accuracy=0.0,
        status_message="Preparing dataset...",
        error=None
    )
    with _train_lock:
        _train_status["logs"] = ["Preparing dataset..."]
    
    t = threading.Thread(target=_train_run, args=(epochs, batch_size, lr, train_type), daemon=True)
    t.start()
    return True, "Training started."

def calculate_per_class_metrics(preds, targets, losses, categories):
    """
    preds: 1D torch.Tensor of predictions
    targets: 1D torch.Tensor of ground truth targets
    losses: 1D torch.Tensor of losses per sample
    categories: list of category names
    """
    results = {}
    for c_idx, cat in enumerate(categories):
        # Samples belonging to this class
        class_mask = (targets == c_idx)
        class_count = class_mask.sum().item()
        
        if class_count == 0:
            results[cat] = {
                "count": 0,
                "loss": 0.0,
                "acc": 0.0,
                "f1": 0.0
            }
            continue
            
        # Class-specific loss
        class_loss = losses[class_mask].mean().item()
        
        # True Positives: predicted c_idx and target is c_idx
        tp = ((preds == c_idx) & class_mask).sum().item()
        
        # False Positives: predicted c_idx but target is NOT c_idx
        fp = ((preds == c_idx) & ~class_mask).sum().item()
        
        # False Negatives: predicted NOT c_idx but target is c_idx
        fn = ((preds != c_idx) & class_mask).sum().item()
        
        # Recall / Accuracy for this class
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        
        # Precision
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        
        # F1
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        results[cat] = {
            "count": class_count,
            "loss": class_loss,
            "acc": recall,
            "f1": f1
        }
    return results

def _train_run(epochs, batch_size, lr, train_type="cnn"):
    # Import torchvision inside function to save startup memory
    import torchvision.models as models
    from torchvision import transforms
    
    try:
        dataset_root = os.path.join("data", "dataset")
        if not os.path.exists(dataset_root):
            raise Exception("Dataset directory 'data/dataset/' does not exist. Please review some images first.")
            
        # Collect all categories (candidate mapping)
        candidate_categories = []
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    candidate_categories = json.load(f).get("categories", [])
            except Exception as e:
                print(f"Error loading config.json: {e}")
                
        # Also query sqlite DB for any reviewed labels to cover custom DB labels
        try:
            from backend.db import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT corrected_label FROM records WHERE reviewed = 1 AND corrected_label IS NOT NULL")
            db_categories = [row[0] for row in cursor.fetchall()]
            conn.close()
            for db_cat in db_categories:
                if db_cat not in candidate_categories:
                    candidate_categories.append(db_cat)
        except Exception as e:
            print(f"Error loading categories from DB: {e}")
            
        # Filter candidate categories to those that actually have images in their safe folders on disk
        categories = []
        for cat in candidate_categories:
            safe_dir = get_safe_dir_name(cat)
            cat_dir = os.path.join(dataset_root, safe_dir)
            if os.path.exists(cat_dir):
                imgs = glob.glob(os.path.join(cat_dir, "*.jpg")) + glob.glob(os.path.join(cat_dir, "*.png")) + glob.glob(os.path.join(cat_dir, "*.jpeg"))
                if len(imgs) > 0:
                    categories.append(cat)
                    
        # Fallback to check for any unmapped directories physically on disk
        try:
            existing_dirs = [d for d in os.listdir(dataset_root) if os.path.isdir(os.path.join(dataset_root, d))]
        except Exception:
            existing_dirs = []
            
        for d in existing_dirs:
            mapped = False
            for cat in candidate_categories:
                if get_safe_dir_name(cat) == d:
                    mapped = True
                    break
            if not mapped:
                cat_dir = os.path.join(dataset_root, d)
                imgs = glob.glob(os.path.join(cat_dir, "*.jpg")) + glob.glob(os.path.join(cat_dir, "*.png")) + glob.glob(os.path.join(cat_dir, "*.jpeg"))
                if len(imgs) > 0:
                    categories.append(d)
                    
        if not categories:
            raise Exception("No categories with images found in dataset. Please review and correct some images first.")
            
        image_paths = []
        labels = []
        for cat in categories:
            safe_dir = get_safe_dir_name(cat)
            cat_dir = os.path.join(dataset_root, safe_dir)
            imgs = glob.glob(os.path.join(cat_dir, "*.jpg")) + glob.glob(os.path.join(cat_dir, "*.png")) + glob.glob(os.path.join(cat_dir, "*.jpeg"))
            image_paths.extend(imgs)
            labels.extend([cat] * len(imgs))
            
        num_images = len(image_paths)
        print(f"Found {num_images} images across {len(categories)} categories.")
        
        if num_images < 5:
            raise Exception(f"Insufficient data: Found only {num_images} images. Please correct and review at least 5 images before training.")
            
        # Create class mapping
        label_to_idx = {cat: idx for idx, cat in enumerate(categories)}
        idx_to_label = {idx: cat for idx, cat in enumerate(categories)}
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        if train_type in ["clip_mlp", "clip_linear"]:
            model_type = "linear" if train_type == "clip_linear" else "mlp"
            
            # Save labels metadata structure
            os.makedirs("models", exist_ok=True)
            labels_data = {
                "categories": categories,
                "model_type": model_type
            }
            with open(os.path.join("models", "clip_mlp_labels.json"), "w", encoding="utf-8") as f:
                json.dump(labels_data, f, indent=4, ensure_ascii=False)
                
            update_training_status(status_message="Extracting CLIP embeddings...")
            
            # Import functions locally
            from backend.classifiers import get_clip_features, CLIPMLPClassifier, CLIPLinearClassifier
            
            # Pre-extract features for all images
            features_list = []
            targets_list = []
            
            for i, (img_path, label) in enumerate(zip(image_paths, labels)):
                update_training_status(status_message=f"Extracting features: {i+1}/{num_images} images...")
                try:
                    # CLIP features are pre-normalized, shape (1, 512)
                    feats = get_clip_features(img_path).cpu().squeeze(0)
                    features_list.append(feats)
                    targets_list.append(label_to_idx[label])
                except Exception as e:
                    print(f"Skipping image {img_path} due to extraction error: {e}")
                    
            if len(features_list) < 5:
                raise Exception(f"Insufficient successfully processed images. Only {len(features_list)} succeeded.")
                
            features_tensor = torch.stack(features_list)  # shape (N, 512)
            targets_tensor = torch.tensor(targets_list, dtype=torch.long)  # shape (N,)
            
            num_extracted = len(features_list)
            
            # Setup K-Fold Cross Validation
            K = 5
            if num_extracted < K:
                K = max(2, num_extracted // 2)
                
            print(f"Starting {K}-Fold Cross Validation for {train_type} classifier...")
            
            indices = torch.randperm(num_extracted).tolist()
            fold_size = num_extracted // K
            folds = []
            for k in range(K):
                start = k * fold_size
                end = (k + 1) * fold_size if k < K - 1 else num_extracted
                folds.append(indices[start:end])
                
            best_weights = []
            fold_accuracies = []
            
            total_epochs = K * epochs
            update_training_status(total_epochs=total_epochs)
            
            for fold in range(K):
                # Split train / validation for this fold
                val_indices = folds[fold]
                train_indices = [idx for k, f in enumerate(folds) if k != fold for idx in f]
                
                train_dataset = MLPDataset(features_tensor[train_indices], targets_tensor[train_indices])
                val_dataset = MLPDataset(features_tensor[val_indices], targets_tensor[val_indices])
                
                # Weighted sampler for class imbalance
                train_targets = targets_tensor[train_indices]
                class_counts = torch.bincount(train_targets, minlength=len(categories))
                class_weights = 1.0 / class_counts.float()
                class_weights[torch.isinf(class_weights)] = 0.0
                sample_weights = class_weights[train_targets]
                sampler = torch.utils.data.WeightedRandomSampler(
                    weights=sample_weights,
                    num_samples=len(sample_weights),
                    replacement=True
                )
                
                train_loader = DataLoader(train_dataset, batch_size=min(batch_size, len(train_dataset)), sampler=sampler)
                val_loader = DataLoader(val_dataset, batch_size=min(batch_size, len(val_dataset)), shuffle=False)
                
                # Initialize model for this fold
                if model_type == "linear":
                    model = CLIPLinearClassifier(input_dim=512, num_classes=len(categories)).to(device)
                else:
                    model = CLIPMLPClassifier(input_dim=512, hidden_dim=128, num_classes=len(categories)).to(device)
                    
                criterion = nn.CrossEntropyLoss()
                # Increase weight decay to 1e-1 to strongly regularize decision boundaries
                optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-1)
                
                from torch.optim.lr_scheduler import CosineAnnealingLR
                scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)
                
                best_fold_acc = 0.0
                best_fold_weights = None
                
                for epoch in range(1, epochs + 1):
                    current_global_epoch = fold * epochs + epoch
                    update_training_status(
                        current_epoch=current_global_epoch,
                        status_message=f"Fold {fold+1}/{K} | Epoch {epoch}/{epochs}: Training..."
                    )
                    
                    model.train()
                    total_train_loss = 0.0
                    for feats, targets in train_loader:
                        feats = feats.to(device)
                        targets = targets.to(device)
                        
                        optimizer.zero_grad()
                        outputs = model(feats)
                        loss = criterion(outputs, targets)
                        loss.backward()
                        optimizer.step()
                        
                        total_train_loss += loss.item() * feats.size(0)
                        
                    avg_train_loss = total_train_loss / len(train_dataset)
                    scheduler.step()
                    
                    # Validation
                    model.eval()
                    total_val_loss = 0.0
                    correct = 0
                    
                    with torch.no_grad():
                        for feats, targets in val_loader:
                            feats = feats.to(device)
                            targets = targets.to(device)
                            
                            outputs = model(feats)
                            loss = criterion(outputs, targets)
                            total_val_loss += loss.item() * feats.size(0)
                            
                            _, predicted = outputs.max(1)
                            correct += predicted.eq(targets).sum().item()
                            
                    avg_val_loss = total_val_loss / len(val_dataset)
                    val_accuracy = correct / len(val_dataset) if len(val_dataset) > 0 else 0.0
                    
                    if val_accuracy >= best_fold_acc:
                        best_fold_acc = val_accuracy
                        best_fold_weights = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                        
                    update_training_status(
                        train_loss=avg_train_loss,
                        val_loss=avg_val_loss,
                        val_accuracy=val_accuracy
                    )
                    
                print(f"Fold {fold+1}/{K} Completed. Best Val Acc: {best_fold_acc:.4f}")
                best_weights.append(best_fold_weights)
                fold_accuracies.append(best_fold_acc)
                
            # Perform Weighted Stochastic Weight Averaging (SWA) based on fold accuracies
            total_acc = sum(fold_accuracies)
            if total_acc > 0:
                blend_weights = [acc / total_acc for acc in fold_accuracies]
            else:
                blend_weights = [1.0 / K] * K
                
            print(f"Blending fold models. Weights: {[f'{w:.4f}' for w in blend_weights]}")
            
            blended_state_dict = {}
            first_weights = best_weights[0]
            for key in first_weights.keys():
                blended_state_dict[key] = torch.zeros_like(first_weights[key], dtype=torch.float32)
                for w, fw in zip(blend_weights, best_weights):
                    blended_state_dict[key] += w * fw[key]
                    
            # Save blended weights
            model_save_path = os.path.join("models", "clip_mlp_classifier.pth")
            torch.save(blended_state_dict, model_save_path)
            
            # Load SWA weights to evaluate on full dataset
            model.load_state_dict(blended_state_dict)
            model.to(device)
            model.eval()
            with torch.no_grad():
                features_tensor = features_tensor.to(device)
                targets_tensor = targets_tensor.to(device)
                outputs = model(features_tensor)
                
                criterion_none = nn.CrossEntropyLoss(reduction='none')
                sample_losses = criterion_none(outputs, targets_tensor)
                
                _, preds = outputs.max(1)
                
                metrics = calculate_per_class_metrics(preds, targets_tensor, sample_losses, categories)
                
                # Log metrics to stdout and to training logs
                add_training_log("="*50)
                add_training_log("各类别评估指标 (SWA融合模型训练集/全量数据评估):")
                for cat, m in metrics.items():
                    add_training_log(
                        f"类别: {cat:<15} | 样本数: {m['count']:<4} | "
                        f"平均Loss: {m['loss']:.4f} | "
                        f"准确率(召回率): {m['acc']*100:.2f}% | "
                        f"F1-Score: {m['f1']*100:.2f}%"
                    )
                add_training_log("="*50)
            
            # Clear caches
            import backend.classifiers as classifiers
            classifiers._mlp_model = None
            classifiers._mlp_labels = None
            
            update_training_status(
                is_training=False,
                status_message=f"Training completed successfully! Blended {K}-Fold SWA model saved.",
            )
            print("Weighted Fold-Averaged Training finished successfully.")
            
        else:
            # Save categories mapping for CNN inference
            os.makedirs("models", exist_ok=True)
            with open(os.path.join("models", "cnn_labels.json"), "w", encoding="utf-8") as f:
                json.dump(categories, f, indent=4, ensure_ascii=False)
                
            # Setup transforms
            # Robust augmentations for small datasets
            train_transform = transforms.Compose([
                transforms.Resize(256),
                transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.05),
                transforms.RandomAffine(degrees=10, translate=(0.05, 0.05), scale=(0.95, 1.05)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            
            val_transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            
            # Simple train-val split (e.g. 80-20)
            indices = torch.randperm(num_images).tolist()
            split_idx = int(num_images * 0.8)
            
            if split_idx >= num_images:
                split_idx = num_images - 1
            if split_idx <= 0:
                split_idx = 1
                
            train_indices = indices[:split_idx]
            val_indices = indices[split_idx:]
            
            train_paths = [image_paths[i] for i in train_indices]
            train_labels = [labels[i] for i in train_indices]
            val_paths = [image_paths[i] for i in val_indices]
            val_labels = [labels[i] for i in val_indices]
            
            train_dataset = DeskwatchDataset(train_paths, train_labels, label_to_idx, transform=train_transform)
            val_dataset = DeskwatchDataset(val_paths, val_labels, label_to_idx, transform=val_transform)
            
            # WeightedRandomSampler to handle class imbalance
            train_targets = torch.tensor([label_to_idx[l] for l in train_labels], dtype=torch.long)
            class_counts = torch.bincount(train_targets, minlength=len(categories))
            class_weights = 1.0 / class_counts.float()
            class_weights[torch.isinf(class_weights)] = 0.0
            sample_weights = class_weights[train_targets]
            sampler = torch.utils.data.WeightedRandomSampler(
                weights=sample_weights,
                num_samples=len(sample_weights),
                replacement=True
            )
            
            train_loader = DataLoader(train_dataset, batch_size=min(batch_size, len(train_dataset)), sampler=sampler, drop_last=False)
            val_loader = DataLoader(val_dataset, batch_size=min(batch_size, len(val_dataset)), shuffle=False)
            
            update_training_status(status_message="Loading pre-trained ConvNeXt model...")
            
            # Load ConvNeXt
            try:
                from torchvision.models import convnext_tiny, ConvNeXt_Tiny_Weights
                model = convnext_tiny(weights=ConvNeXt_Tiny_Weights.DEFAULT)
            except ImportError:
                model = models.convnext_tiny(pretrained=True)
                
            # Modify final classifier layer
            in_features = model.classifier[2].in_features
            model.classifier[2] = nn.Linear(in_features, len(categories))
            
            model.to(device)
            
            criterion = nn.CrossEntropyLoss()
            
            # Discriminative learning rate: backbone parameters get a 10x lower learning rate
            optimizer_groups = [
                {"params": model.features.parameters(), "lr": lr * 0.1},
                {"params": model.classifier.parameters(), "lr": lr}
            ]
            optimizer = torch.optim.AdamW(optimizer_groups, lr=lr, weight_decay=1e-2)
            
            # Cosine Annealing Learning Rate scheduler
            from torch.optim.lr_scheduler import CosineAnnealingLR
            scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)
            
            # Determine when to disable augmentation (final epochs)
            disable_aug_epoch = max(1, epochs - 2)
            
            print(f"Training started on device: {device}. LLRD and Cosine Scheduler active.")
            
            for epoch in range(1, epochs + 1):
                if epoch > disable_aug_epoch:
                    train_dataset.transform = val_transform
                    status_msg = f"Epoch {epoch}/{epochs} (无增强收敛): Training..."
                else:
                    train_dataset.transform = train_transform
                    status_msg = f"Epoch {epoch}/{epochs} (数据增强中): Training..."
                    
                update_training_status(current_epoch=epoch, status_message=status_msg)
                
                # Training phase
                model.train()
                total_train_loss = 0.0
                for imgs, targets in train_loader:
                    imgs = imgs.to(device)
                    targets = targets.to(device)
                    
                    optimizer.zero_grad()
                    outputs = model(imgs)
                    loss = criterion(outputs, targets)
                    loss.backward()
                    optimizer.step()
                    
                    total_train_loss += loss.item() * imgs.size(0)
                    
                avg_train_loss = total_train_loss / len(train_dataset)
                scheduler.step()
                
                # Validation phase
                update_training_status(status_message=f"Epoch {epoch}/{epochs}: Evaluating...")
                model.eval()
                total_val_loss = 0.0
                correct = 0
                total = 0
                
                with torch.no_grad():
                    for imgs, targets in val_loader:
                        imgs = imgs.to(device)
                        targets = targets.to(device)
                        
                        outputs = model(imgs)
                        loss = criterion(outputs, targets)
                        total_val_loss += loss.item() * imgs.size(0)
                        
                        _, predicted = outputs.max(1)
                        total += targets.size(0)
                        correct += predicted.eq(targets).sum().item()
                        
                avg_val_loss = total_val_loss / len(val_dataset)
                val_accuracy = correct / total if total > 0 else 0.0
                
                update_training_status(
                    train_loss=avg_train_loss,
                    val_loss=avg_val_loss,
                    val_accuracy=val_accuracy
                )
                print(f"Epoch {epoch}/{epochs} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | Val Acc: {val_accuracy:.4f}")
                
            # Save ConvNeXt Model
            model_save_path = os.path.join("models", "cnn_classifier.pth")
            torch.save(model.state_dict(), model_save_path)
            
            update_training_status(status_message="Calculating final metrics on full dataset...")
            eval_dataset = DeskwatchDataset(image_paths, labels, label_to_idx, transform=val_transform)
            eval_loader = DataLoader(eval_dataset, batch_size=min(batch_size, len(eval_dataset)), shuffle=False)
            
            model.eval()
            all_preds = []
            all_targets = []
            all_losses = []
            criterion_none = nn.CrossEntropyLoss(reduction='none')
            
            with torch.no_grad():
                for imgs, targets in eval_loader:
                    imgs = imgs.to(device)
                    targets = targets.to(device)
                    outputs = model(imgs)
                    
                    losses = criterion_none(outputs, targets)
                    _, preds = outputs.max(1)
                    
                    all_preds.append(preds)
                    all_targets.append(targets)
                    all_losses.append(losses)
            
            all_preds = torch.cat(all_preds)
            all_targets = torch.cat(all_targets)
            all_losses = torch.cat(all_losses)
            
            metrics = calculate_per_class_metrics(all_preds, all_targets, all_losses, categories)
            
            # Log metrics to stdout and to training logs
            add_training_log("="*50)
            add_training_log("各类别评估指标 (全量数据评估):")
            for cat, m in metrics.items():
                add_training_log(
                    f"类别: {cat:<15} | 样本数: {m['count']:<4} | "
                    f"平均Loss: {m['loss']:.4f} | "
                    f"准确率(召回率): {m['acc']*100:.2f}% | "
                    f"F1-Score: {m['f1']*100:.2f}%"
                )
            add_training_log("="*50)
            
            # Clear cache
            import backend.classifiers as classifiers
            classifiers._cnn_model = None
            classifiers._cnn_labels = None
            
            update_training_status(
                is_training=False,
                status_message="Training completed successfully! Model saved.",
            )
            print("Training finished successfully.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_training_status(
            is_training=False,
            status_message="Training failed.",
            error=str(e)
        )
        print(f"Training failed: {e}")
