"""
CrewAI tools for the support agent. They wrap catalog.py and log every result,
so answer_check.py can verify that each price / stock number the agent says
really came from a tool.
"""
import json
from typing import Literal, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import knowledge
from catalog import get_product, search_products


class ToolLog:
    """Everything the tools returned during one conversation."""

    def __init__(self):
        self.products: dict[int, dict] = {}   # id -> last data seen for that product
        self.calls: list[dict] = []
        self.skills_used: list[str] = []      # filled by agent.py from crewai's SkillUsedEvent
        self.human_answers: list[dict] = []   # answers from the knowledge base the agent saw
        self.saved_questions: list[dict] = []  # questions it handed to a specialist

    def add(self, tool: str, args: dict, products: list[dict]):
        self.calls.append({"tool": tool, "args": args, "ids": [p["id"] for p in products]})
        for p in products:
            self.products[p["id"]] = {**self.products.get(p["id"], {}), **p}


def _availability(qty: int) -> str:
    return f"in stock ({qty} pcs)" if qty > 0 else "out of stock"


def _summary(p: dict) -> dict:
    keep = {k: v for k, v in p.items() if v is not None and k not in ("description", "short_description", "parameters")}
    keep["is_led"] = bool(p.get("is_led"))
    keep["bulbs_included"] = {1: "yes", 0: "no"}.get(p.get("bulbs_included"), "not specified")
    keep["availability"] = _availability(p["quantity"])
    return keep


class SearchInput(BaseModel):
    query: Optional[str] = Field(None, description="Free words, e.g. 'candle bulb', 'chandelier', 'Philips', 'RGB LED strip'")
    socket: Optional[str] = Field(None, description="Lamp socket / base, e.g. E27, E14, GU10, G9, G13, GU5.3")
    category: Optional[str] = Field(None, description=(
        "Part of the category path. BULBS (what goes into a socket, incl. GU10/MR16 'spots', candles, tubes) are "
        "under 'Light bulbs' ('Light bulbs > LED', '> Halogen', '> Fluorescent', '> Incandescent', "
        "'> Energy-saving (CFL)'). FIXTURES: 'Chandeliers', 'Ceiling', 'Wall lights', 'Table lamps', 'Floor lamps', "
        "'Spotlights' (spotlight fixtures, not bulbs), 'Outdoor lighting', 'Outdoor lighting > Wall', 'Bollards', "
        "'Floodlights', 'Fluorescent fixtures'. OTHER: 'LED strips', 'Garlands', 'Ballasts', 'Motion sensors', "
        "'Transformers', 'Lamp holders'. It is the kind of product being BOUGHT ('a sensor for outdoor lights' -> "
        "'Motion sensors', not 'Outdoor lighting'). Leave it empty if unsure -- the free words also find the right type."))
    is_led: Optional[bool] = Field(None, description="True = LED only, False = no LED")
    min_ip: Optional[int] = Field(None, description="Minimum IP rating, e.g. 44 for bathrooms and outdoors")
    min_power_w: Optional[float] = Field(None, description="Minimum power in watts (per lamp / bulb)")
    max_power_w: Optional[float] = Field(None, description="Maximum power in watts (per lamp / bulb)")
    voltage: Optional[int] = Field(None, description="Lamp voltage, e.g. 12 for spots on a transformer, 230 for mains")
    light_colour: Optional[Literal["warm", "neutral", "daylight", "cold"]] = Field(None, description="Light colour of bulbs")
    finish_colour: Optional[str] = Field(None, description="Colour of the fixture, e.g. chrome, black, white, bronze")
    min_price: Optional[float] = Field(None, description="Minimum price in EUR")
    max_price: Optional[float] = Field(None, description="Maximum price in EUR")
    in_stock_only: bool = Field(False, description="True = hide products with quantity 0. Usually leave False: "
                                "in-stock products are already listed first, and a customer asking about a "
                                "specific product must hear its real availability.")
    limit: int = Field(6, ge=1, le=10, description="How many products to return (max 10)")


class SearchProductsTool(BaseTool):
    name: str = "search_products"
    description: str = ("Search the shop catalogue. Combine free words with filters. Returns a short list of "
                        "products with id, name, category, socket, power, IP rating, price_eur and availability. "
                        "Returns [] if nothing matches -- then try fewer filters.")
    args_schema: Type[BaseModel] = SearchInput
    log: ToolLog

    def _run(self, **kwargs) -> str:
        args = {k: v for k, v in kwargs.items() if v is not None}
        rows = search_products(**args)
        self.log.add(self.name, args, rows)
        if not rows:
            filters = [k for k in args if k not in ("query", "limit")]
            return json.dumps({"results": [], "hint": (
                f"Nothing matched ALL of these filters: {filters}. This does NOT mean the shop has no such "
                "product. Search again with fewer filters (drop category / in_stock_only / light_colour first) "
                "before telling the customer anything is unavailable.")})
        return json.dumps([_summary(r) for r in rows], ensure_ascii=False)


class ProductInput(BaseModel):
    product_id: int = Field(..., description="The product id from search_products")


class GetProductDetailsTool(BaseTool):
    name: str = "get_product_details"
    description: str = ("Full details of one product: price in EUR, quantity in stock, all specs and the shop's "
                        "own description. Use it before you state the price or availability of a product.")
    args_schema: Type[BaseModel] = ProductInput
    log: ToolLog

    def _run(self, product_id: int) -> str:
        p = get_product(int(product_id))
        if not p:
            self.log.add(self.name, {"product_id": product_id}, [])
            return json.dumps({"error": f"no product with id {product_id}"})
        self.log.add(self.name, {"product_id": product_id}, [p])
        out = _summary(p)
        out["short_description"], out["description"] = p["short_description"], p["description"]
        return json.dumps(out, ensure_ascii=False)


class QuestionInput(BaseModel):
    question: str = Field(..., description="The customer's question, written as a clear stand-alone question "
                                           "(include the details that matter, e.g. the city or product)")


class SearchAnsweredQuestionsTool(BaseTool):
    name: str = "search_answered_questions"
    description: str = ("Search answers that the shop's specialists wrote to earlier customer questions "
                        "(delivery, returns, warranty, installation, compatibility...). Returns similar earlier "
                        "questions with their answers, best match first. A similar question is not always the "
                        "same question: use an answer only if it really answers what THIS customer asked.")
    args_schema: Type[BaseModel] = QuestionInput
    log: ToolLog

    def _run(self, question: str) -> str:
        found = knowledge.search_answered(question)
        self.log.calls.append({"tool": self.name, "args": {"question": question}, "ids": [f["id"] for f in found]})
        self.log.human_answers += found
        if not found:
            return json.dumps({"results": [], "hint": "No specialist has answered a similar question yet. "
                               "Save it with save_difficult_question."})
        return json.dumps(found, ensure_ascii=False)


class SaveQuestionInput(QuestionInput):
    reason: str = Field("", description="Why you could not answer it yourself, in a few words")


class SaveDifficultQuestionTool(BaseTool):
    name: str = "save_difficult_question"
    description: str = ("Hand a question you cannot answer to a human specialist. Use it when neither the "
                        "catalogue, nor your skills, nor search_answered_questions gives a real answer. "
                        "The same question asked again is counted, not duplicated.")
    args_schema: Type[BaseModel] = SaveQuestionInput
    log: ToolLog

    def _run(self, question: str, reason: str = "") -> str:
        saved = knowledge.save_question(question, reason)
        self.log.calls.append({"tool": self.name, "args": {"question": question, "reason": reason}, "ids": []})
        self.log.saved_questions.append(saved)
        return json.dumps(saved)


def make_tools(log: ToolLog) -> list[BaseTool]:
    return [SearchProductsTool(log=log), GetProductDetailsTool(log=log),
            SearchAnsweredQuestionsTool(log=log), SaveDifficultQuestionTool(log=log)]
