import os
import json
import pdfplumber
import anthropic
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MONDAY_API_KEY = os.environ.get("MONDAY_API_KEY")
MONDAY_BOARD_ID = os.environ.get("MONDAY_BOARD_ID", "18390622308")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def extrair_texto_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
    return texto

def extrair_dados_nf(texto):
    prompt = (
        "Voce e um especialista em notas fiscais brasileiras.\n"
        "Analise o texto abaixo de uma NF-e e extraia as informacoes em JSON.\n\n"
        "Retorne APENAS um JSON valido, sem explicacoes, sem markdown, sem backticks.\n\n"
        "Formato esperado:\n"
        '{"numero_nf": "000.071.604", "data_emissao": "2026-06-03", "fornecedor": "Nome do fornecedor", '
        '"canal_compra": "Mercado Livre", "itens": [{"nome": "Nome do produto", "quantidade": 1, "valor_unitario": 346.64}]}\n\n'
        "Para canal_compra, tente identificar se e: Mercado Livre, Magazine Luiza, Shopee, Amazon, Americanas, Loja Fisica, ou Outro.\n"
        "Se nao conseguir identificar, coloque Nao identificado.\n\n"
        "Texto da NF:\n" + texto
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    resposta = message.content[0].text.strip()
    return json.loads(resposta)

def criar_item_monday(item, numero_nf, data_emissao, responsavel, local, canal_compra):
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }

    data_formatada = data_emissao if data_emissao else ""

    column_values = json.dumps({
        "data": {"date": data_formatada},
        "text_mm4gqxsy": numero_nf,
        "numeric_mky8bk22": item["valor_unitario"],
        "numeric_mm2wge9s": item["quantidade"],
        "text_mm4f77m6": canal_compra,
