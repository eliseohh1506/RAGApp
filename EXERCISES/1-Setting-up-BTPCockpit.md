# Setup SAP BTP Cockpit 

In this section, we will be setting up your BTP Cockpit to allow for connectivity with **AI Launchpad, Document Extraction, SAP HANA Cloud and S3 Object Store.** Thereafter we will proceed to modify the sample_env.txt file with the required keys. 

## STEP 1: Open SAP Business Technology Platform

👉 Open SAP [BTP Cockpit](https://emea.cockpit.btp.cloud.sap/cockpit).

👉 Navigate to your subaccount. If creating a new subaccount, ensure region chosen allows provisioning of all pre-requisite services. [View Regions to see more](https://help.sap.com/docs/btp/sap-business-technology-platform/regions).

## STEP 2: Open SAP AI Launchpad and connect to SAP AI Core

👉 Go to Instances and Subscriptions.

Check whether you see an SAP AI Core service instance and an SAP AI Launchpad application subscription. Ensure your AI Core service instance runs on the ``extended`` plan to access capailities of Generative AI Hub.

> SAP AI Launchpad is a centralised platform for AI lifecycle managemenet. We will be using it to deploy our LLM models for chunking and embedding conversion. 

👉 If you haven't created an AI Core instance, go to Service Marketplace and search for SAP AI Core -> Click Create, choose ``extended`` plan, Cloud Foundry runtime environment and give it an instance name. -> Create instance 

![AICore](assets/AICore_create.png)

👉 Click into the new AI Core instance you've created, if there's no service key already, click create a new one and give your service key a name. No need to input any JSON, just click Create.

![AICore_Servicekey](assets/AICore_servicekey.png)

👉 If you haven't created an AI Launchpad Subscription, go to Service Marketplace and search for SAP AI Launchpad -> Click Create

![AI Launchpad](assets/AILaunchpad_create.png)

## STEP 3: Connect to Document Information Extraction Service 

👉 Go to Instances and Subscriptions.

Check whether you see an Document Information Extraction instance as well as subscription. Ensure your Document Information Extraction service instance runs on the ``premium_edition`` plan to process custom documents using generative AI.

👉 If you haven't created an Document Information Extraction instance or subscription, go to Service Marketplace and search for Document Information Extraction -> Click Create, choose service plan of ``premium_edition`` and click create. 

👉 For Subscription, go to Service Marketplace and search for Document Information Extraction -> Click Create, choose subscription plan of ``default`` and click create. 
