import numpy as np

from mlkeras.data import make_dataset, scale
from mlkeras.model import build_model, load, predict_labels, save, set_seed, train


def _trained():
    set_seed(0)
    x_tr, x_te, y_tr, y_te = make_dataset()
    x_tr, x_te = scale(x_tr, x_te)
    model = build_model()
    history = train(model, x_tr, y_tr, epochs=8)
    return model, history, x_te, y_te


def test_dataset_shapes():
    x_tr, x_te, y_tr, y_te = make_dataset()
    assert x_tr.shape == (300, 8) and x_te.shape == (100, 8)
    assert set(np.unique(y_tr)) <= {0, 1}


def test_model_learns_simple_rule():
    model, history, x_te, y_te = _trained()
    assert history.history["loss"][-1] < history.history["loss"][0]
    accuracy = (predict_labels(model, x_te) == y_te).mean()
    assert accuracy > 0.8


def test_save_and_load_roundtrip(tmp_path):
    model, _, x_te, _ = _trained()
    path = tmp_path / "model.h5"
    save(model, str(path))
    restored = load(str(path))
    np.testing.assert_allclose(model.predict(x_te, verbose=0), restored.predict(x_te, verbose=0), rtol=1e-5)
