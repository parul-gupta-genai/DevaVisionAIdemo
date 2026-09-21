import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import numpy as np
from pathlib import Path

CROPS_DIR = Path("/home/claude/helmet_crops")
IMG_SIZE = (96, 96)
BATCH_SIZE = 32
CLASS_NAMES = ["helmet", "no-helmet"]


def make_dataset(split, shuffle):
    ds = keras.utils.image_dataset_from_directory(
        CROPS_DIR / split,
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=shuffle,
        seed=42,
    )
    return ds


train_ds = make_dataset("train", shuffle=True)
val_ds = make_dataset("val", shuffle=False)
test_ds = make_dataset("test", shuffle=False)

# class weights for the ~3:1 helmet:no-helmet imbalance seen in extraction
n_helmet, n_nohelmet = 11982, 3748
total = n_helmet + n_nohelmet
class_weight = {
    0: total / (2 * n_helmet),      # helmet
    1: total / (2 * n_nohelmet),    # no-helmet (weighted up)
}
print("class_weight:", class_weight)

normalization = layers.Rescaling(1.0 / 255)

data_augmentation = keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.03),
    layers.RandomBrightness(0.08),
])

AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.map(lambda x, y: (data_augmentation(normalization(x), training=True), y),
                         num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)
val_ds = val_ds.map(lambda x, y: (normalization(x), y), num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)
test_ds = test_ds.map(lambda x, y: (normalization(x), y), num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)

model = keras.Sequential([
    layers.Input(shape=(*IMG_SIZE, 3)),
    layers.Conv2D(32, 3, padding="same", activation="relu"),
    layers.BatchNormalization(),
    layers.MaxPooling2D(),
    layers.Conv2D(64, 3, padding="same", activation="relu"),
    layers.BatchNormalization(),
    layers.MaxPooling2D(),
    layers.Conv2D(128, 3, padding="same", activation="relu"),
    layers.BatchNormalization(),
    layers.MaxPooling2D(),
    layers.Conv2D(128, 3, padding="same", activation="relu"),
    layers.BatchNormalization(),
    layers.GlobalAveragePooling2D(),
    layers.Dropout(0.3),
    layers.Dense(64, activation="relu"),
    layers.Dropout(0.2),
    layers.Dense(1, activation="sigmoid"),
])

# Lower LR than the first (failed) attempt: that run's loss oscillated
# around ln(2)=0.693 for 5 straight epochs — the signature of a model that
# never leaves the "predict the prior" local minimum, usually because the
# optimizer step size is too large for a from-scratch CNN on this little
# data. BatchNorm + a gentler LR fixes that instability. Early
# stopping/checkpointing on val_loss now, not val_recall — val_recall hits a
# trivial 1.0 by always predicting "no-helmet", which is exactly what sank
# the first run (test precision == the no-helmet class's prior, recall
# stuck at 1.0 — a constant-output model, not a trained one).
model.compile(
    optimizer=keras.optimizers.Adam(learning_rate=3e-4),
    loss=keras.losses.BinaryCrossentropy(label_smoothing=0.05),
    metrics=["accuracy", keras.metrics.Precision(name="precision"),
             keras.metrics.Recall(name="recall")],
)
model.summary()

callbacks = [
    keras.callbacks.EarlyStopping(monitor="val_loss", mode="min", patience=6, restore_best_weights=True),
    keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-6),
    keras.callbacks.ModelCheckpoint("/home/claude/helmet_classifier_best.keras",
                                     monitor="val_loss", mode="min", save_best_only=True),
]

history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=25,
    class_weight=class_weight,
    callbacks=callbacks,
    verbose=2,
)

print("\n=== TEST SET EVALUATION ===")
results = model.evaluate(test_ds, verbose=2)
for name, val in zip(model.metrics_names, results):
    print(f"{name}: {val:.4f}")

model.save("/home/claude/helmet_classifier_final.keras")
print("\nSaved to /home/claude/helmet_classifier_final.keras "
      "(and best-val-recall checkpoint at helmet_classifier_best.keras)")
