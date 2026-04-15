# Entity Linking Laboratory

Prerequisites:

If you want to use the GPU (recommended), you need CUDA

This app can be deployed in two ways:
1. Docker:

    `cd docker`
    
    `docker compose up --build`

2. Local:

    cd to the project directory

    `python3 -m venv venv`
    
    `source venv/bin/activate`
    
    `pip install -r requirements.txt`
    
    `python3 app.py`


Then you can access the app at http://localhost:5000/