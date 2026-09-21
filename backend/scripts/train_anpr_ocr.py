import json
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

CROPS_DIR = "/home/claude/anpr_ocr_crops_v2"
IMG_H, IMG_W = 32, 128
CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CHAR_TO_IDX = {c: i for i, c in enumerate(CHARSET)}
IDX_TO_CHAR = {i: c for i, c in enumerate(CHARSET)}
BLANK_IDX = len(CHARSET)  # CTC blank token, index 36
MAX_LABEL_LEN = 13
BATCH_SIZE = 32

manifest = json.load(open(f"{CROPS_DIR}/manifest.json"))


def load_split(split):
    paths = [p for p, _ in manifest[split]]
    texts = [t for _, t in manifest[split]]
    return paths, texts


def encode_label(text):
    ids = [CHAR_TO_IDX[c] for c in text]
    length = len(ids)
    ids = ids + [BLANK_IDX] * (MAX_LABEL_LEN - length)  # pad with blank, ignored via label_length
    return np.array(ids, dtype=np.int32), length


def make_arrays(paths, texts):
    images = np.zeros((len(paths), IMG_H, IMG_W, 1), dtype=np.float32)
    labels = np.full((len(paths), MAX_LABEL_LEN), BLANK_IDX, dtype=np.int32)
    label_lengths = np.zeros((len(paths),), dtype=np.int32)
    for i, (p, t) in enumerate(zip(paths, texts)):
        img = keras.utils.load_img(p, color_mode="grayscale", target_size=(IMG_H, IMG_W))
        arr = keras.utils.img_to_array(img) / 255.0
        images[i] = arr
        ids, length = encode_label(t)
        labels[i] = ids
        label_lengths[i] = length
    return images, labels, label_lengths


print("Loading data into memory (dataset is small enough)...")
train_paths, train_texts = load_split("train")
val_paths, val_texts = load_split("val")
test_paths, test_texts = load_split("test")

X_train, y_train, ylen_train = make_arrays(train_paths, train_texts)
X_val, y_val, ylen_val = make_arrays(val_paths, val_texts)
X_test, y_test, ylen_test = make_arrays(test_paths, test_texts)
print(f"train={len(X_train)} val={len(X_val)} test={len(X_test)}")


# --- Model: CNN feature extractor -> BiLSTM sequence -> per-timestep softmax ---
# Width 128 -> pooled by 4 (2x, then 2x) -> 32 timesteps, comfortably more
# than MAX_LABEL_LEN=13 as CTC requires (output steps >= label length).

def build_model():
    inputs = layers.Input(shape=(IMG_H, IMG_W, 1), name="image")
    x = layers.Conv2D(32, 3, padding="same", activation="relu")(inputs)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2, 2))(x)  # 16 x 64
    x = layers.Conv2D(64, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2, 2))(x)  # 8 x 32
    x = layers.Conv2D(128, 3, padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2, 1))(x)  # 4 x 32 — only pool height further, keep width (time) resolution

    # (batch, 4, 32, 128) -> (batch, 32, 4*128): width becomes the time axis
    shape = x.shape
    x = layers.Permute((2, 1, 3))(x)  # (batch, 32, 4, 128)
    x = layers.Reshape((shape[2], shape[1] * shape[3]))(x)  # (batch, 32, 512)
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.2)(x)

    x = layers.Bidirectional(layers.LSTM(128, return_sequences=True, dropout=0.2))(x)
    x = layers.Bidirectional(layers.LSTM(64, return_sequences=True, dropout=0.2))(x)

    # +1 for the CTC blank class
    y_pred = layers.Dense(len(CHARSET) + 1, activation="softmax", name="softmax")(x)
    return keras.Model(inputs=inputs, outputs=y_pred, name="anpr_ocr_crnn")


base_model = build_model()
base_model.summary()
time_steps = base_model.output_shape[1]
print(f"Model time steps: {time_steps} (must be >= MAX_LABEL_LEN={MAX_LABEL_LEN})")


class CTCLossModel(keras.Model):
    """Wraps the base model to compute CTC loss during training via a
    custom train_step, while keeping the base model's plain
    (image -> per-timestep softmax) signature for inference/decoding."""

    def __init__(self, base):
        super().__init__()
        self.base = base
        self.loss_tracker = keras.metrics.Mean(name="loss")

    @property
    def metrics(self):
        # Keras 3 uses this list to know which trackers to reset each epoch
        # and which to read for the progress bar / history — returning a
        # raw tensor from train_step (what the first version of this script
        # did) silently displayed as 0.0000e+00 despite real gradients
        # flowing; this is the correct way to surface a custom loss.
        return [self.loss_tracker]

    def call(self, inputs, training=False):
        return self.base(inputs, training=training)

    def train_step(self, data):
        images, labels, label_lengths = data
        batch_size = tf.shape(images)[0]
        input_length = tf.fill([batch_size, 1], time_steps)
        label_length = tf.expand_dims(label_lengths, axis=1)

        with tf.GradientTape() as tape:
            y_pred = self.base(images, training=True)
            loss = tf.keras.backend.ctc_batch_cost(labels, y_pred, input_length, label_length)
            loss = tf.reduce_mean(loss)

        grads = tape.gradient(loss, self.base.trainable_variables)
        self.optimizer.apply_gradients(zip(grads, self.base.trainable_variables))
        self.loss_tracker.update_state(loss)
        return {"loss": self.loss_tracker.result()}

    def test_step(self, data):
        images, labels, label_lengths = data
        batch_size = tf.shape(images)[0]
        input_length = tf.fill([batch_size, 1], time_steps)
        label_length = tf.expand_dims(label_lengths, axis=1)
        y_pred = self.base(images, training=False)
        loss = tf.keras.backend.ctc_batch_cost(labels, y_pred, input_length, label_length)
        self.loss_tracker.update_state(tf.reduce_mean(loss))
        return {"loss": self.loss_tracker.result()}


def make_tf_dataset(images, labels, label_lengths, shuffle):
    ds = tf.data.Dataset.from_tensor_slices((images, labels, label_lengths))
    if shuffle:
        ds = ds.shuffle(len(images), seed=42)
    return ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)


train_ds = make_tf_dataset(X_train, y_train, ylen_train, shuffle=True)
val_ds = make_tf_dataset(X_val, y_val, ylen_val, shuffle=False)

model = CTCLossModel(base_model)
model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3))

callbacks = [
    keras.callbacks.EarlyStopping(monitor="val_loss", mode="min", patience=8, restore_best_weights=True),
    keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-6),
]

history = model.fit(train_ds, validation_data=val_ds, epochs=60, callbacks=callbacks, verbose=2)

base_model.save("/home/claude/anpr_ocr_model.keras")
print("\nSaved base (inference) model to /home/claude/anpr_ocr_model.keras")


def ctc_greedy_decode(y_pred):
    input_len = np.ones(y_pred.shape[0]) * y_pred.shape[1]
    decoded, _ = tf.keras.backend.ctc_decode(y_pred, input_length=input_len, greedy=True)
    decoded = decoded[0].numpy()
    texts = []
    for seq in decoded:
        chars = [IDX_TO_CHAR[i] for i in seq if 0 <= i < len(CHARSET)]
        texts.append("".join(chars))
    return texts


def evaluate(X, texts, name):
    preds_prob = base_model.predict(X, verbose=0)
    preds = ctc_greedy_decode(preds_prob)
    exact = sum(1 for p, t in zip(preds, texts) if p == t)
    char_acc_sum = 0.0
    for p, t in zip(preds, texts):
        if not t:
            continue
        matches = sum(1 for a, b in zip(p, t) if a == b)
        char_acc_sum += matches / max(len(p), len(t))
    print(f"\n=== {name} SET ===")
    print(f"Exact match: {exact}/{len(texts)} = {exact/len(texts)*100:.1f}%")
    print(f"Char accuracy: {char_acc_sum/len(texts)*100:.1f}%")
    print("Sample predictions:")
    for p, t in list(zip(preds, texts))[:10]:
        mark = "✓" if p == t else "✗"
        print(f"  {mark} truth={t:12s} pred={p:12s}")
    return preds


evaluate(X_val, val_texts, "VALIDATION")
evaluate(X_test, test_texts, "TEST")
