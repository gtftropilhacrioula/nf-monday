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

def criar_item_monday(item, numero_nf, data_emissao, local, canal_compra):
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
        "dropdown_mm2s9w16": {"labels": [local]},
        "color_mm4g90ps": {"index": 0},
    })

    query = "mutation ($board: ID!, $item_name: String!, $column_values: JSON!) { create_item(board_id: $board, item_name: $item_name, column_values: $column_values) { id } }"

    variables = {
        "board": int(MONDAY_BOARD_ID),
        "item_name": item["nome"],
        "column_values": column_values
    }

    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    result = response.json()
    return result["data"]["create_item"]["id"]

def anexar_pdf_monday(item_id, pdf_bytes, filename):
    url = "https://api.monday.com/v2/file"
    headers = {"Authorization": MONDAY_API_KEY}

    query = "mutation ($file: File!) { add_file_to_column(item_id: %s, column_id: \"file_mky8cexx\", file: $file) { id } }" % item_id

    files = {
        "query": (None, query),
        "variables[file]": (filename, pdf_bytes, "application/pdf")
    }

    response = requests.post(url, headers=headers, files=files)
    return response.json()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("pdf")
        if not file:
            return jsonify({"erro": "Nenhum arquivo enviado"}), 400
        texto = extrair_texto_pdf(file)
        dados = extrair_dados_nf(texto)
        return jsonify(dados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/enviar", methods=["POST"])
def enviar():
    try:
        data = request.form
        pdf_file = request.files.get("pdf")
        pdf_bytes = pdf_file.read() if pdf_file else None
        pdf_name = pdf_file.filename if pdf_file else "nota_fiscal.pdf"

        itens = json.loads(data.get("itens", "[]"))
        numero_nf = data.get("numero_nf", "")
        data_emissao = data.get("data_emissao", "")
        local = data.get("local", "")
        canal_compra = data.get("canal_compra", "")

        item_ids = []
        for item in itens:
            item_id = criar_item_monday(item, numero_nf, data_emissao, local, canal_compra)
            item_ids.append(item_id)

        if pdf_bytes:
            for item_id in item_ids:
                anexar_pdf_monday(item_id, pdf_bytes, pdf_name)

        return jsonify({"sucesso": True, "total": len(item_ids)})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
