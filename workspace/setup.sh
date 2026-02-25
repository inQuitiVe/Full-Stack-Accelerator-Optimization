pip install hydra-core
pip install botorch
pip install "ax-platform==0.3.5"
pip install "numpy==1.26.4"
pip install rich
git clone --recurse-submodules https://github.com/Accelergy-Project/accelergy-timeloop-infrastructure.git
cd accelergy-timeloop-infrastructure
make install_accelergy
pip3 install ./src/timeloopfe
pip install pytorch-metric-learning