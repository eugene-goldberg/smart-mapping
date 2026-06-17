[[_TOC_]]  
[[_TOSP_]]  
  
---  
  
## Project Description  
  
**AI-Enabled Disclosures** extends the Disclosure Management module with AI-powered position and report suggestions. When a user opens the position or report selection wizard inside a Disclosure Response question, the system automatically ranks and surfaces the most relevant candidates using locally-running ML models — presented as a confidence-scored suggestion panel above the standard search list.  
  
The feature is built on a **privacy-first** principle: all AI inference runs inside the application's own Docker infrastructure. No customer data is sent to any external service or LLM.  
  
  
## Team(s)  
  
| Role | Owner |  
|---|---|  
| Project lead | @<B6423F85-C77D-6B00-931B-2013D296DB8D> |  
| Branch | `feature/disclosure_ai/m1` |  
| Base branch | `development` |  
| Deploy target | `sofi-feature3` (Azure Pipelines) |  
  
---  
  
## Architecture  
[C2 Component Diagram](https://app.moqups.com/j6NJGn1DHhhwJyH6OsjcDSSIoxgceePo/edit/page/aa90a43e4)

**What Disclosure AI does**
It helps suggest relevant reporting positions or report fields when a user is filling out a disclosure questionnaire. The suggestion pipeline has two stages:
1.  **Embedding (bi-encoder)** — Every position/report in the database is converted into a numerical vector ("embedding") that captures its meaning. When a user asks a question, their query is also converted to a vector, and the closest matches are retrieved quickly using vector similarity. This is fast but imprecise — it returns a broad set of ~60 candidates.
    
2.  **Reranking (cross-encoder)** — The candidates from step 1 are passed through a second, more accurate model that compares the query and each candidate together (not independently). It scores them precisely and returns the top ~10, filtered by confidence thresholds.
    
* * *

## What is embedding?
Embedding is a means of representing objects like text, images and audio as points in a continuous vector space where the locations of those points in space are semantically meaningful to [machine learning (ML) algorithms

Embedding is a critical tool for ML engineers who build text and image search engines, recommendation systems, chatbots, fraud detection systems and many other applications. In essence, embedding enables machine learning.

![embedding.png](/.attachments/embedding-2ab3b0e6-a0a2-4557-801f-87c1eb77780f.png)

## What is re-ranking?

Re-ranking is a sophisticated technique used to enhance the relevance of search results by using the advanced language understanding capabilities of LLMs.

Initially, a set of candidate documents or passages is retrieved using traditional information retrieval methods like BM25 or vector similarity search. These candidates are then fed into an LLM that analyzes the semantic relevance between the query and each document. The LLM assigns relevance scores, enabling the re-ordering of documents to prioritize the most pertinent ones.

This process significantly improves the quality of search results by going beyond mere keyword matching to understand the context and meaning of the query and documents.
Re-ranking is typically used as a second stage after an initial fast retrieval step, ensuring that only the most relevant documents are presented to the user. It can also combine results from multiple data sources, as well as integrate in a RAG pipeline to further ensure that context is ideally tuned for the specific query.

![two-step-workflow-embedding-model-reranking-model-rag-pipeline.png](/.attachments/two-step-workflow-embedding-model-reranking-model-rag-pipeline-5eb1f48a-50c6-4836-8ab6-427d75d76aa2.png)

## Data Flow
![AI Suggestion Data Flow](/.attachments/Screenshot%202026-05-22%20at%2009.35.05-5639365d-1219-4638-99c2-19741a7facd8.png)
## Additional Resources  
  
| What | Where |  
|---|---|
| What is embedding? | [What is embedding?](https://www.ibm.com/think/topics/embedding) |  
| What is reranking? | [ What is reranking?](https://developer.nvidia.com/blog/how-using-a-reranking-microservice-can-improve-accuracy-and-costs-of-information-retrieval/) |
| ONNX Concepts | [https://onnx.ai/onnx/intro/concepts.html](https://onnx.ai/onnx/intro/concepts.html) |
| RAG Reranking Explained | [RAG Reranking Explained: How To Improve RAG Results](https://www.youtube.com/@pixegami)| [](https://www.youtube.com/watch?v=R5MPqm0V6aQ)
