pip install hydra-core
pip install botorch
pip install "ax-platform==0.3.5"
pip install "numpy==1.26.4"
pip install rich
cd accelergy-timeloop-infrastructure
git submodule sync --recursive
git submodule update --init src/accelergy
git submodule update --init src/timeloopfe
pip install ./src/accelergy
pip install ./src/timeloopfe
cd ..
pip install pytorch-metric-learning
pip install pymoo
python3 fix_accelergy_config.py