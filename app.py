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
    prompt = f"""Você é um especialista em notas fiscais brasileiras.
Analise o texto abaixo de uma NF-e e extraia as informações em JSON.

Retorne APENAS um JSON válido, sem explicações, sem markdown, sem backticks.

Formato esperado:
{{
  "numero_nf": "000.071.604",
  "data_emissao": "2026-06-03",
  "fornecedor": "Nome do fornecedor",
  "canal_compra": "Mercado Livre",
  "itens": [
    {{
      "nome": "Nome do produto",
      "quantidade": 1,
      "valor_unitario": 346.64
    }}
  ]
}}

Para canal_compra, tente identificar se é: Mercado Livre, Magazine Luiza, Shopee, Amazon, Americanas, Loja Física, ou Outro.
Se não conseguir identificar, coloque "Não identificado".

Texto da NF:
{texto}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{{"role": "user", "content": prompt}}]
    )
    
    resposta = message.content[0].text.strip()
    return json.loads(resposta)

def inserir_item_monday(item, numero_nf, data_emissao, responsavel, local, canal_compra):
    url = "https://api.monday.com/v2"
    headers = {{
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }}
    
    column_values = json.dumps({{
        "date4": {{"date": data_emissao}},
        "text6": numero_nf,
        "numbers": item["valor_unitario"],
        "numeric": item["quantidade"],
        "canal_de_compra": {{"text": canal_compra}},
    }})

    query = """
    mutation ($board: ID!, $item_name: String!, $column_values: JSON!) {{
      create_item(
        board_id: $board,
        item_name: $item_name,
        column_values: $column_values
      ) {{
        id
      }}
    }}
    """
    
    variables = {{
        "board": int(MONDAY_BOARD_ID),
        "item_name": item["nome"],
        "column_values": column_values
    }}

    response = requests.post(url, json={{"query": query, "variables": variables}}, headers=headers)
    return response.json()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("pdf")
        if not file:
            return jsonify({{"erro": "Nenhum arquivo enviado"}}), 400
        texto = extrair_texto_pdf(file)
        dados = extrair_dados_nf(texto)
        return jsonify(dados)
    except Exception as e:
        return jsonify({{"erro": str(e)}}), 500

@app.route("/enviar", methods=["POST"])
def enviar():
    try:
        data = request.json
        itens = data.get("itens", [])
        numero_nf = data.get("numero_nf", "")
        data_emissao =
