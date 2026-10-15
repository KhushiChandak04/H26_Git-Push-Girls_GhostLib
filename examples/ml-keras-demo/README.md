# ml-keras-demo — a GhostLib ML migration target

A deliberately small TensorFlow/Keras project with the problems real ML repositories accumulate:

- **Pins from the TensorFlow 2.10 era:** `tensorflow==2.10.0`, `keras==2.10.0`, `numpy==1.23.5`, `scikit-learn==1.1.3`
  and `h5py==3.7.0`. These have no installable builds for Python 3.12/3.13, even where their metadata says otherwise.
- **Keras-2-only API:** `keras.optimizers.Adam(lr=...)` stops working in Keras 3, which only accepts `learning_rate`.
- **A real test suite:** it trains a tiny model on synthetic data and checks the learning, predictions and the
  `.h5` save/load round-trip.

GhostLib copies this folder to `targets/ml-keras-demo` (its own git repository) and scans it like any other
project. See the README section "Machine-learning stacks" for the results.
