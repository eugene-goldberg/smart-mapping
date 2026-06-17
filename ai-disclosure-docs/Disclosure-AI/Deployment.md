[[_TOC_]]

## Automatic Deployment
The automatic deployment would be possible by adding the feature branch to the azure build package pipeline:

.azure-pipelines/azure-pipelines-packages.yml
```
trigger:
  - feature/disclosure_ai/m1

stages:
  - stage: Build
    jobs:
      - job: PrepareApplicationEnvironment
        variables:
          ${{ if and(contains(variables['Build.SourceBranch'], 'refs/heads/feature/disclosure_ai/m1'), eq(variables['Build.Reason'], 'IndividualCI')) }} :
            HOST_GROUP: sofi-feature3
```
**Note**: Before merging the feature branch with "development" this should be reverted.

## Manual Deployment
Follow the below link to run the "Build Package" pipeline:
https://dev.azure.com/sphera/Sphera%20Cloud%20Corporate%20Sustainability/_build?definitionId=1588

**Branch**: feature/disclosure_ai/m1
**Host**: sofi-feature3


**What the script (app/bin/disclosure_ai_start.sh) does at deploy time**
1.  **Install Python packages** — installs the runtime dependencies (numpy, ONNX Runtime, etc.) into `/data/usr/local` so they're accessible to the web server user.
2.  **Export ONNX models** (once only) — converts the HuggingFace PyTorch bi-encoder and cross-encoder models into the faster ONNX format. This happens only if the `.onnx` file doesn't exist yet.
3.  **Run the indexer** — pre-computes and stores embeddings for all positions and reports into the database, so the PHP backend can retrieve them at query time without computing them on the fly.
