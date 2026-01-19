<instructions>
Perform the itemized task items using the specific task overview while keeping the project-level goals and objectives in mind. There are design choices that have been delegated to you - do research before making your choice and present a summary after they have been implemented. 
</instructions>
<Project_Overview>
This solution aims to create an AI/LLM/Transformer-based solutions development environment using kubernetes. 
</Project_Overview>
<Project_Objectives>
- Embed observability through all development-enabling services and all deployed solutions 
- Assist user with the creation on AI systems 
- Ensure base services are compatible with LLM and agentic frameworks
</Project_Objectives>
<Task_Overview>
Add prometheus, grafana, a timeseries database (you choose), ray services, and ui services to the kubernetes deployment. Then create a plan of attack to implement these changes and update relevant documentation. Where possible, configure the deployments to enable integration with agentic libraries
</Task_Overview>
<Task_Items>
- Add prometheus and all required/related resources
- Add grafana and all required/related resources
- Add a timeseries database of your choosing that integrates with prometheus and vector storage (if possible)
- Fix jaeger and integrate with prometheus and timeseries database
- Add persistent vector store
- Add base MLFlow tables, ensure the deployment is pointing to the database deployments; search the web if issues arise
- Add support for loki 
- Add support for chroma vector store
- Add support for argo workflows 
- add support for bentoml deployments
</Task_Items>
<Requirements>
- Enhance the observability and integrate the new services into the existing framework
- Solve jaeger issue where the lack of a database and prometheus deployment caused problems
</Requirements>
<Delegated_Design_Decisions>
- Timeseries database with prometheus compatibility
- Vector store (if chromadb is not the ideal database)
</Delegated_Design_Decisions>