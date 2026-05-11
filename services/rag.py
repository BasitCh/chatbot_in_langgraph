import base64
import os

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith.run_helpers import tracing_context

from core.config import CHROMA_PERSIST_DIR

SUPPORTED_DOCS = {".pdf", ".txt", ".docx", ".doc"}
SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOC_LOADERS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".docx": Docx2txtLoader,
    ".doc": Docx2txtLoader,
}


class RagService:
    def __init__(self) -> None:
        self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self._vision = ChatOpenAI(model="gpt-4o")
        self._splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=250)
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        self._store = Chroma(
            embedding_function=self._embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

    def ingest(self, file_path: str, filename: str) -> int:
        ext = os.path.splitext(filename)[-1].lower()
        if ext in SUPPORTED_DOCS:
            chunks = self._chunks_from_doc(file_path, ext)
        elif ext in SUPPORTED_IMAGES:
            chunks = self._chunks_from_image(file_path, filename)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        self._store.add_documents(chunks)
        return len(chunks)

    def retrieve(self, query: str) -> str:
        # MMR (max marginal relevance) picks `k` chunks that are both
        # relevant AND diverse from a larger `fetch_k` candidate pool. For a
        # resume this surfaces Projects + Experience + Skills sections on a
        # single query, instead of 5 near-duplicate Experience chunks.
        results = self._store.max_marginal_relevance_search(
            query, k=10, fetch_k=30, lambda_mult=0.5
        )
        if not results:
            return "No documents or images uploaded yet."
        return "\n\n---\n\n".join(doc.page_content for doc in results)

    def _chunks_from_doc(self, file_path: str, ext: str) -> list[Document]:
        docs = DOC_LOADERS[ext](file_path).load()
        return self._splitter.split_documents(docs)

    def _chunks_from_image(self, file_path: str, filename: str) -> list[Document]:
        ext = os.path.splitext(filename)[-1].lower().lstrip(".")
        media_type = f"image/{'jpeg' if ext == 'jpg' else ext}"

        with open(file_path, "rb") as f:
            image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        # Disable LangSmith tracing for this call so the multi-MB base64 image
        # payload never gets uploaded to api.smith.langchain.com.
        with tracing_context(enabled=False):
            response = self._vision.invoke(
                [
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": (
                                    "Describe this image in full detail. Include all "
                                    "visible text, numbers, charts, objects and layout."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                            },
                        ]
                    )
                ]
            )

        doc = Document(page_content=response.content, metadata={"source": filename})
        return self._splitter.split_documents([doc])


_rag: RagService | None = None


def get_rag() -> RagService:
    global _rag
    if _rag is None:
        _rag = RagService()
    return _rag
