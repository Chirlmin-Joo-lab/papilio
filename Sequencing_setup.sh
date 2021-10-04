#!/bin/bash
pwd
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3.sh
bash ~/miniconda3.sh -b -p $HOME/miniconda3
rm ~/miniconda3.sh
~/miniconda3/condabin/conda env create -f sequencing_environment.yml