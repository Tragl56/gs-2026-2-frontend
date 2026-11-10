"""Modelos Pydantic de entrada e saída da API de relatos."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    buraco = "buraco_via"
    iluminacao = "iluminacao"
    lixo = "lixo_entulho"
    alagamento = "alagamento"
    arvore = "arvore_risco"
    calcada = "calcada_acessibilidade"
    sinalizacao = "sinalizacao_transito"
    outro = "outro"


class Urgency(str, Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


class Status(str, Enum):
    aberto = "aberto"
    em_andamento = "em_andamento"
    resolvido = "resolvido"
    rejeitado = "rejeitado"


CATEGORY_INFO: dict[Category, dict[str, str]] = {
    Category.buraco: {"label": "Buraco na via", "department": "Secretaria de Obras e Vias", "icon": "🕳️"},
    Category.iluminacao: {"label": "Iluminação pública", "department": "Departamento de Iluminação Pública", "icon": "💡"},
    Category.lixo: {"label": "Lixo ou entulho", "department": "Limpeza Urbana", "icon": "🗑️"},
    Category.alagamento: {"label": "Alagamento", "department": "Defesa Civil e Drenagem", "icon": "🌊"},
    Category.arvore: {"label": "Árvore com risco", "department": "Secretaria do Verde e Meio Ambiente", "icon": "🌳"},
    Category.calcada: {"label": "Calçada / acessibilidade", "department": "Subprefeitura – Manutenção de Calçadas", "icon": "♿"},
    Category.sinalizacao: {"label": "Sinalização de trânsito", "department": "Companhia de Engenharia de Tráfego", "icon": "🚦"},
    Category.outro: {"label": "Outro problema", "department": "Central de Atendimento 156", "icon": "📌"},
}


# ---------- Entrada do cidadão ----------

class ReportInput(BaseModel):
    description: str = Field(..., min_length=20, max_length=1000, description="Relato do cidadão")
    cep: str | None = Field(default=None, description="CEP com 8 dígitos (opcional)")
    reference: str | None = Field(default=None, max_length=150, description="Ponto de referência")

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 20:
            raise ValueError("Descreva o problema com pelo menos 20 caracteres.")
        return v

    @field_validator("cep")
    @classmethod
    def validate_cep(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 8:
            raise ValueError("O CEP deve ter 8 dígitos.")
        return digits


# ---------- Saída estruturada do LLM ----------

class LLMTriage(BaseModel):
    """Formato exato exigido do LLM (response_schema)."""
    category: Category
    urgency: Urgency
    title: str = Field(..., description="Título curto do problema, até 60 caracteres")
    summary: str = Field(..., description="Resumo objetivo em 1 ou 2 frases")
    citizen_guidance: list[str] = Field(..., description="2 a 4 orientações práticas ao cidadão")
    safety_alert: str = Field(..., description="Alerta de risco imediato; string vazia se não houver")
    confidence: float = Field(..., ge=0, le=1)


class Location(BaseModel):
    cep: str
    street: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""


class TriageResult(LLMTriage):
    """Resultado entregue ao front: triagem da IA + dados enriquecidos."""
    category_label: str
    category_icon: str
    department: str
    response_deadline_hours: int
    location: Location | None = None
    anonymized: bool = False
    similar_open: int = 0  # relatos abertos parecidos (mesma categoria e local)


# ---------- Confirmação (human-in-the-loop) ----------

class ReportCreate(BaseModel):
    input: ReportInput
    triage: TriageResult | None = Field(
        default=None, description="Triagem da IA; ausente quando o cidadão registra sem a IA (IA fora do ar)")
    final_category: Category
    final_urgency: Urgency


class Feedback(BaseModel):
    useful: bool
    comment: str | None = Field(default=None, max_length=300)


class StatusUpdate(BaseModel):
    status: Status
    manager_note: str | None = Field(default=None, max_length=300)


class Report(BaseModel):
    id: int
    protocol: str
    created_at: datetime
    description: str
    cep: str | None
    reference: str | None
    location: Location | None
    ai_category: Category | None
    ai_urgency: Urgency | None
    final_category: Category
    final_urgency: Urgency
    corrected_by_citizen: bool
    ai_used: bool = True
    category_label: str
    department: str
    title: str
    summary: str
    status: Status = Status.aberto
    manager_note: str | None = None
    feedback_useful: bool | None = None
    feedback_comment: str | None = None


class PublicRecord(BaseModel):
    """Versão anonimizada de um relato para o painel público (sem texto nem CEP)."""
    created_at: datetime
    category: Category
    category_label: str
    urgency: Urgency
    status: Status
    neighborhood: str
    corrected_by_citizen: bool
    ai_used: bool


class CategoryOut(BaseModel):
    value: Category
    label: str
    department: str
    icon: str
