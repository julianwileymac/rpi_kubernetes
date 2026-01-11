<Project_Background>
This project focuses on a 4 node raspberry pi kubernetes cluster and handles setup, management, and development (through example projects and containerized python services/environments). These are deployed on a local network for use as a personal development lab. There is a 5th node in the form of an Ubuntu desktop.
</Project_Background>
<TasK_Overview>
Your task is to create the initial resources to deploy the base services to the kubernetes cluster, setup the hardware, and create a base control panel/service to manage the Kubernetes cluster, deployed applications, and the underlying hardware. 
</Task_Overview>
<Task_Items>
- Create project structure
- Create bootstrap scripts to setup the hardware. Explain the paramters and use config files for reproducibility for each node
- Create artifacts to deploy the base services and any other recommended ones; Use Tavily to find any instructions
- Write a simple python management framework and control panel for kubernetes, the underlying machines, and any deployments. Create any web components needed (node + next JS components )
- Ensure a simple ML Flow Component is compatible with the local framework (check the .index to find context and relevant locations)
- Connect the services to the framework; add context in documents and a skeleton framework to enable a future project to expand the functionality 
- Embed opentelemetry tracing where possible, add a simple grafana+prometheus dashboard for monitoring
- Deploy Jupyterhub and expose for development via remote machine on the local network - add bootstraping scripts and explanations 
</Task_Items>
<Base_Services>
- JupyterHub
- Minio (or other storage service)
- Postgresql 
- Grafana
- Prometheus
- MLFLow 
- Dask/Ray
</Base_Services>
<Local_Framework_Project>
C:\Users\Julian Wiley\Documents\GitHub\agentic_assistants
</Local_Framework_Project>