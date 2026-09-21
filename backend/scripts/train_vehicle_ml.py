import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import joblib

data = json.load(open("/home/claude/vehicle_features.json"))


def to_matrix(rows, feature_names):
    return np.array([[r[k] for k in feature_names] for r in rows])


feature_names = sorted(data["train"]["rows"][0].keys())
print(f"features ({len(feature_names)}): {feature_names}")

X_train = to_matrix(data["train"]["rows"], feature_names)
y_train = np.array(data["train"]["labels"])
X_val = to_matrix(data["val"]["rows"], feature_names)
y_val = np.array(data["val"]["labels"])
X_test = to_matrix(data["test"]["rows"], feature_names)
y_test = np.array(data["test"]["labels"])

# Simple oversampling of the minority class (tractor, 96 of 344 train
# examples) with small Gaussian jitter in feature space — a lightweight
# alternative to SMOTE that still gives the trees/SVM more tractor-labeled
# examples to split on, without needing extra dependencies.
rng = np.random.RandomState(42)
minority_mask = y_train == 0  # tractor
minority_X = X_train[minority_mask]
n_majority = (y_train == 1).sum()
n_minority = minority_mask.sum()
n_to_add = n_majority - n_minority
if n_to_add > 0:
    idx = rng.choice(len(minority_X), size=n_to_add, replace=True)
    feature_std = X_train.std(axis=0) * 0.05  # 5% jitter, keeps samples plausible
    jitter = rng.normal(0, 1, size=(n_to_add, X_train.shape[1])) * feature_std
    synth_X = minority_X[idx] + jitter
    X_train = np.vstack([X_train, synth_X])
    y_train = np.concatenate([y_train, np.zeros(n_to_add, dtype=int)])
    print(f"Oversampled tractor: {n_minority} -> {n_minority + n_to_add} "
          f"(added {n_to_add} jittered synthetic examples)")

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s = scaler.transform(X_val)
X_test_s = scaler.transform(X_test)

models = {
    "random_forest": RandomForestClassifier(
        n_estimators=300, max_depth=6, min_samples_leaf=4,
        random_state=42, n_jobs=-1,
    ),
    "gradient_boosting": GradientBoostingClassifier(
        n_estimators=150, max_depth=2, learning_rate=0.05, random_state=42,
    ),
    "svm_rbf": SVC(kernel="rbf", C=1.0, probability=True, random_state=42),
}

best_name, best_model, best_val_acc = None, None, 0.0
for name, model in models.items():
    model.fit(X_train_s, y_train)
    val_pred = model.predict(X_val_s)
    val_acc = accuracy_score(y_val, val_pred)
    print(f"\n=== {name} ===")
    print(f"val accuracy: {val_acc:.3f}")
    print(classification_report(y_val, val_pred, target_names=["tractor", "truck"]))
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        best_name, best_model = name, model

print(f"\nBest model on val: {best_name} ({best_val_acc:.3f})")

test_pred = best_model.predict(X_test_s)
test_acc = accuracy_score(y_test, test_pred)
print(f"\n=== FINAL TEST RESULTS ({best_name}) ===")
print(f"test accuracy: {test_acc:.3f}")
print(classification_report(y_test, test_pred, target_names=["tractor", "truck"]))
print("confusion matrix [tractor, truck] (rows=true, cols=pred):")
print(confusion_matrix(y_test, test_pred))

if hasattr(best_model, "feature_importances_"):
    importances = sorted(zip(feature_names, best_model.feature_importances_), key=lambda x: -x[1])
    print("\ntop features by importance:")
    for name, imp in importances[:10]:
        print(f"  {name}: {imp:.3f}")

out_path = "/home/claude/vehicle_classifier.joblib"
joblib.dump(
    {"model": best_model, "scaler": scaler, "feature_names": feature_names,
     "classes": ["tractor", "truck"], "test_accuracy": test_acc,
     "val_accuracy": best_val_acc, "model_type": best_name},
    out_path,
)
print(f"\nSaved to {out_path}")
