import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def make_dataset(n=400, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 8)).astype("float32")
    y = (x[:, 0] + 0.5 * x[:, 1] > 0).astype("int32")
    return train_test_split(x, y, test_size=0.25, random_state=seed)


def scale(x_train, x_test):
    scaler = StandardScaler().fit(x_train)
    return scaler.transform(x_train).astype("float32"), scaler.transform(x_test).astype("float32")
