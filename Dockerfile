FROM quay.io/fenicsproject/stable:latest

RUN pip install --user h5py

RUN git clone https://github.com/geo-fluid-dynamics/phaseflow-fenics.git

RUN cd phaseflow-fenics && pip install --user . && cd ~