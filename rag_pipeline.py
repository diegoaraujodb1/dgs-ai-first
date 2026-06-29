from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


DEFAULT_COLLECTION = "novatech_docs"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_PERSIST_DIR = Path(".chroma")
DEFAULT_INPUT_DIR = Path("anexo-a-documentos-individuais")
DEFAULT_EVAL_FILE = Path("tests") / "coverage_questions.json"
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "que",
    "se",
    "um",
    "uma",
}


@dataclass
class DocumentChunk:
    chunk_id: str
    source: str
    section: str
    version: str
    authority: str
    text: str

    def metadata(self) -> dict[str, str]:
        return {
            "source": self.source,
            "section": self.section,
            "version": self.version,
            "authority": self.authority,
        }


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def slugify(value: str) -> str:
    simplified = value.lower()
    replacements = {
        "ã": "a",
        "á": "a",
        "à": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for original, replacement in replacements.items():
        simplified = simplified.replace(original, replacement)
    simplified = re.sub(r"[^a-z0-9]+", "-", simplified)
    return simplified.strip("-") or "secao"


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    raise ValueError(f"Formato nao suportado: {path.suffix}")


def extract_metadata_header(text: str, path: Path) -> tuple[str, str, str]:
    version = search_header_value(text, "Versao") or search_header_value(text, "Versão") or "desconhecida"
    classification = search_header_value(text, "Classificacao") or search_header_value(text, "Classificação") or "nao informado"
    authority = "informal" if "NÃO validado" in text or "NAO validado" in text or "Documento informal" in text else "formal"
    if "FAQ" in path.stem.upper():
        authority = "informal"
    return version, classification, authority


def search_header_value(text: str, header_name: str) -> str | None:
    pattern = re.compile(rf"\*\*{re.escape(header_name)}:\*\*\s*(.+)")
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return None


def extract_document_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def linearize_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    normalized_lines: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1

            if len(table_lines) >= 3:
                headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
                for row in table_lines[2:]:
                    values = [cell.strip() for cell in row.strip("|").split("|")]
                    pairs = [f"{header}: {value}" for header, value in zip(headers, values) if header and value]
                    if pairs:
                        normalized_lines.append("; ".join(pairs))
            else:
                normalized_lines.extend(table_lines)
            continue

        normalized_lines.append(line)
        index += 1

    return "\n".join(normalized_lines)


def build_chunk_text(document_title: str, section_title: str, section_body: str) -> str:
    normalized_body = linearize_markdown_tables(section_body)
    return normalize_whitespace(
        f"Documento: {document_title}\nSeção: {section_title}\n\n{normalized_body}"
    )


def tokenize_for_ranking(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9À-ÿ]+", text.lower())
    return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}


def infer_query_hints(question: str) -> set[str]:
    hints = tokenize_for_ranking(question)
    lowered = question.lower()

    if any(term in lowered for term in ["gold", "silver", "standard", "platinum", "sla"]):
        hints.update({"sla", "tier", "tiers", "cliente"})

    if any(term in lowered for term in ["devolução", "devolucao", "devolver"]):
        hints.update({"devolucao", "prazo"})

    if "perigosa" in lowered:
        hints.update({"perigosa", "riscos", "antt"})

    if any(term in lowered for term in ["frete", "kg", "manaus", "salvador", "sudeste", "norte", "nordeste"]):
        hints.update({"frete", "especial", "multiplicador", "regiao"})

    if "manaus" in lowered:
        hints.add("norte")

    if "salvador" in lowered:
        hints.add("nordeste")

    return hints


def compute_domain_boost(question: str, metadata: dict[str, str], text: str) -> float:
    lowered = question.lower()
    source = metadata["source"].lower()
    section = metadata["section"].lower()
    content = text.lower()
    boost = 0.0

    if any(term in lowered for term in ["devolução", "devolucao", "devolver"]):
        if source.startswith("pol-"):
            boost += 0.18
        if "prazo geral" in section:
            boost += 0.12
        if "exce" in section and "perigosa" in lowered:
            boost += 0.12

    if any(term in lowered for term in ["gold", "silver", "standard", "platinum", "sla"]):
        if source.startswith("sla-"):
            boost += 0.18
        if "tabela de slas" in section:
            boost += 0.14
        if "classifica" in section:
            boost += 0.10
        if "platinum" in lowered and "não existem outros tiers" in content:
            boost += 0.15

    if any(term in lowered for term in ["frete", "kg", "manaus", "salvador"]):
        if source.startswith("proc-"):
            boost += 0.18
        if "multiplicadores regionais" in section:
            boost += 0.16
        if "fórmula de cálculo" in section or "formula de calculo" in section:
            boost += 0.12
        if "v2" in source:
            boost += 0.06

    if "perigosa" in lowered and source.startswith("faq-") and "item 3" in section:
        boost += 0.08

    return boost


def compute_ranking_score(question: str, metadata: dict[str, str], text: str, semantic_similarity: float) -> float:
    query_terms = infer_query_hints(question)
    text_terms = tokenize_for_ranking(text)
    section_terms = tokenize_for_ranking(metadata["section"])

    if not query_terms:
        return semantic_similarity

    lexical_overlap = len(query_terms & text_terms) / len(query_terms)
    section_overlap = len(query_terms & section_terms) / len(query_terms)
    authority_boost = 0.08 if metadata.get("authority") == "formal" else 0.0
    domain_boost = compute_domain_boost(question, metadata, text)

    return semantic_similarity + (0.30 * lexical_overlap) + (0.25 * section_overlap) + authority_boost + domain_boost


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    current_title = "Introducao"
    current_lines: list[str] = []
    sections: list[tuple[str, str]] = []

    for line in text.splitlines():
        heading = re.match(r"^(##+)+\s+(.*)$", line)
        if heading:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_title, body))
            current_title = heading.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append((current_title, body))

    return sections


def split_large_section(section_text: str, max_chars: int = 1200, overlap_paragraphs: int = 1) -> list[str]:
    cleaned = normalize_whitespace(section_text)
    if len(cleaned) <= max_chars:
        return [cleaned]

    paragraphs = [paragraph.strip() for paragraph in cleaned.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(paragraphs):
        current: list[str] = []
        length = 0
        index = start
        while index < len(paragraphs):
            paragraph = paragraphs[index]
            projected = length + len(paragraph) + (2 if current else 0)
            if current and projected > max_chars:
                break
            current.append(paragraph)
            length = projected
            index += 1

        if not current:
            current = [paragraphs[start][:max_chars]]
            index = start + 1

        chunks.append("\n\n".join(current))
        if index >= len(paragraphs):
            break
        start = max(index - overlap_paragraphs, start + 1)

    return chunks


def chunk_document(path: Path) -> list[DocumentChunk]:
    raw_text = read_document(path)
    version, _, authority = extract_metadata_header(raw_text, path)
    document_title = extract_document_title(raw_text, path)
    sections = split_markdown_sections(raw_text)

    chunks: list[DocumentChunk] = []
    base_slug = slugify(path.stem)
    for section_title, section_body in sections:
        content_parts = split_large_section(section_body)
        section_slug = slugify(section_title)
        for part_index, part in enumerate(content_parts, start=1):
            chunk_id = f"{base_slug}-{section_slug}"
            if len(content_parts) > 1:
                chunk_id = f"{chunk_id}-p{part_index}"
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    source=path.name,
                    section=section_title,
                    version=version,
                    authority=authority,
                    text=build_chunk_text(document_title, section_title, part),
                )
            )
    return chunks


class RagPipeline:
    def __init__(
        self,
        persist_dir: Path = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_model: str = DEFAULT_MODEL,
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_model = SentenceTransformer(embedding_model)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    def ingest(self, input_dir: Path) -> dict[str, int]:
        files = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not files:
            raise FileNotFoundError(f"Nenhum documento suportado encontrado em {input_dir}")

        chunks = [chunk for path in files for chunk in chunk_document(path)]
        embeddings = self.embedding_model.encode([chunk.text for chunk in chunks], normalize_embeddings=True).tolist()
        existing_ids = self.collection.get(include=[]).get("ids", [])
        if existing_ids:
            self.collection.delete(ids=existing_ids)
        self.collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata() for chunk in chunks],
            embeddings=embeddings,
        )
        return {"files": len(files), "chunks": len(chunks)}

    def search(self, question: str, top_k: int = 4) -> list[dict[str, object]]:
        query_embedding = self.embedding_model.encode([question], normalize_embeddings=True).tolist()
        candidate_count = max(top_k, self.collection.count())
        result = self.collection.query(query_embeddings=query_embedding, n_results=candidate_count)

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        matches: list[dict[str, object]] = []
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            similarity = 1 - float(distance)
            ranking_score = compute_ranking_score(question, metadata, document, similarity)
            matches.append(
                {
                    "chunk_id": chunk_id,
                    "similarity": round(similarity, 4),
                    "ranking_score": round(ranking_score, 4),
                    "source": metadata["source"],
                    "section": metadata["section"],
                    "version": metadata["version"],
                    "authority": metadata["authority"],
                    "text": document,
                }
            )
        matches.sort(key=lambda item: item["ranking_score"], reverse=True)
        return matches[:top_k]

    def build_prompt(self, question: str, retrieved_chunks: Sequence[dict[str, object]]) -> str:
        context_blocks = []
        for index, chunk in enumerate(retrieved_chunks, start=1):
            context_blocks.append(
                "\n".join(
                    [
                        f"[Chunk {index}] id={chunk['chunk_id']}",
                        f"fonte={chunk['source']} | secao={chunk['section']} | versao={chunk['version']} | autoridade={chunk['authority']} | similaridade={chunk['similarity']}",
                        str(chunk["text"]),
                    ]
                )
            )

        system_prompt = """Voce e um assistente de atendimento da NovaTech.
Responda usando apenas as informacoes presentes nos chunks recuperados.
Se houver conflito entre fontes, priorize documentos formais mais recentes e explicite a divergencia.
Se a informacao nao estiver coberta pelos chunks, diga claramente que nao encontrou base documental suficiente.
Sempre cite os ids dos chunks usados na resposta."""

        return (
            f"{system_prompt}\n\n"
            f"Contexto recuperado:\n\n{chr(10).join(context_blocks)}\n\n"
            f"Pergunta do usuario: {question}\n\n"
            "Resposta:"
        )


def print_search_results(results: Sequence[dict[str, object]]) -> None:
    for item in results:
        print(
            f"- {item['chunk_id']} | similaridade={item['similarity']} | ranking={item['ranking_score']} | fonte={item['source']} | secao={item['section']}"
        )
        print(f"  {item['text']}\n")


def evaluate_coverage(pipeline: RagPipeline, questions_file: Path, top_k: int) -> list[dict[str, object]]:
    payload = json.loads(questions_file.read_text(encoding="utf-8"))
    report: list[dict[str, object]] = []
    for row in payload:
        results = pipeline.search(row["question"], top_k=top_k)
        recovered_sources = [str(item["chunk_id"]) for item in results]
        expected_prefixes = row["expected_chunk_prefixes"]
        matched = all(any(recovered.startswith(prefix) for recovered in recovered_sources) for prefix in expected_prefixes)
        report.append(
            {
                "question": row["question"],
                "expected_chunk_prefixes": expected_prefixes,
                "recovered_chunks": recovered_sources,
                "matched": matched,
                "scores": [item["similarity"] for item in results],
                "ranking_scores": [item["ranking_score"] for item in results],
            }
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POC minima de RAG com ChromaDB e sentence-transformers.")
    parser.add_argument("command", choices=["ingest", "search", "prompt", "evaluate"])
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--persist-dir", type=Path, default=DEFAULT_PERSIST_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--question")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = RagPipeline(
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        embedding_model=args.model,
    )

    if args.command == "ingest":
        stats = pipeline.ingest(args.input_dir)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if args.command == "search":
        if not args.question:
            raise SystemExit("Use --question para buscar.")
        results = pipeline.search(args.question, top_k=args.top_k)
        print_search_results(results)
        return

    if args.command == "prompt":
        if not args.question:
            raise SystemExit("Use --question para montar o prompt.")
        results = pipeline.search(args.question, top_k=args.top_k)
        print(pipeline.build_prompt(args.question, results))
        return

    if args.command == "evaluate":
        report = evaluate_coverage(pipeline, args.eval_file, top_k=args.top_k)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
