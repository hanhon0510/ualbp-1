# SAT Encoding Based Binomial Encoding for Solving UALBP-1 Problem

This project uses a SAT encoding based binomial encoding to solve the UALBP-1 Problem.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

## Requirements and Installation

1. **Python Version**  
   Make sure you have Python 3.8 installed

2. **Virtual Environment**  
   Create and activate a virtual environment:

```bash
py -3.8 -m venv venv38
venv38\Scripts\activate
```

3. **Install Dependency**
   Download and install the pypblib wheel from this link https://github.com/rjungbeck/pypblib/releases/download/pypblib-v1.0.24/pypblib-0.0.4-cp38-cp38-win_amd64.whl, then install the required Python libraries

```bash
pip install D:\path\to\pypblib-0.0.4-cp38-cp38-win_amd64.whl
pip install python-sat[aiger,approxmc,cryptosat,pblib]
pip install pypblib
```

4. **Run the program**
   Run the file you want

```bash
python ualbp_naive.py
```
