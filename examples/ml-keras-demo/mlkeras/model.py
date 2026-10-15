"""A small binary classifier written the way many TensorFlow 2.x / Keras 2 projects were.

It intentionally uses APIs that changed in Keras 3 (e.g. the ``lr`` optimizer argument),
so upgrading TensorFlow/Keras is a real migration, not just a version bump.
"""
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers


def set_seed(seed=0):
    np.random.seed(seed)
    tf.random.set_seed(seed)


def build_model(input_dim=8, lr=0.01):
    model = keras.Sequential([
        layers.Dense(16, activation="relu", input_shape=(input_dim,)),
        layers.Dense(1, activation="sigmoid"),
    ])
    # Keras 2 accepted `lr`; Keras 3 only accepts `learning_rate`.
    model.compile(optimizer=keras.optimizers.Adam(lr=lr), loss="binary_crossentropy", metrics=["accuracy"])
    return model


def train(model, x, y, epochs=5):
    return model.fit(x, y, epochs=epochs, batch_size=32, verbose=0)


def predict_labels(model, x):
    return (model.predict(x, verbose=0) > 0.5).astype("int32").ravel()


def save(model, path):
    model.save(path)


def load(path):
    return keras.models.load_model(path)
