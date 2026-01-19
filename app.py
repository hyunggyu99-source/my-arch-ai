from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import streamlit as st
import google.generativeai as genai
from PIL import Image
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 500000) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            chunks.append(text.strip())
    full_text = "\n\n".join(chunks).strip()
    return full_text[:max_chars]


def analyze_floorplan(image: Image.Image, law_text: str, model_name: str) -> str:
    system_prompt = (
        "You are an architectural compliance assistant. Review the floor plan and "
        "report potential issues or confirmations about building regulations, "
        "such as living room width, presence of windows, and other safety or "
        "habitability checks. If a rule cannot be verified from the image, say so."
    )
    user_prompt = (
        "Use the following regulations text as the source of truth. Analyze this "
        "floor plan for compliance items (e.g., living room width, window presence, "
        "egress). Provide a concise checklist with findings and cite relevant "
        "clauses from the regulations. End your answer with a section titled "
        "'참고 법령 조항' that lists the clauses you referenced.\n\n"
        f"[Regulations]\n{law_text}"
    )

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
    )
    response = model.generate_content([user_prompt, image])
    return response.text.strip()


def resolve_korean_font() -> tuple[str | None, str | None]:
    base_dir = Path(__file__).resolve().parent
    candidates = [
        ("NanumGothic", base_dir / "fonts" / "NanumGothic.ttf"),
        ("NanumGothic", base_dir / "NanumGothic.ttf"),
        ("MalgunGothic", Path("C:/Windows/Fonts/malgun.ttf")),
        ("MalgunGothic", Path("C:/Windows/Fonts/malgunbd.ttf")),
    ]
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, path in candidates:
        if path.exists():
            if name not in registered:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            return name, str(path)
    return None, None


def build_pdf_bytes(
    analysis_text: str,
    plan_filename: str,
    analyzed_at: str,
    font_name: str | None,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    base_font = font_name or "Helvetica"
    title_style = ParagraphStyle(
        "TitleK",
        parent=styles["Title"],
        fontName=base_font,
    )
    body_style = ParagraphStyle(
        "BodyK",
        parent=styles["BodyText"],
        fontName=base_font,
        leading=16,
    )
    story = [
        Paragraph("건축 법규 검토 결과", title_style),
        Spacer(1, 6 * mm),
        Paragraph(f"분석 일시: {escape(analyzed_at)}", body_style),
        Paragraph(f"도면 파일명: {escape(plan_filename)}", body_style),
        Spacer(1, 4 * mm),
        Paragraph("AI 분석 내용:", body_style),
        Spacer(1, 2 * mm),
        Paragraph(escape(analysis_text).replace("\n", "<br/>"), body_style),
    ]
    doc.build(story)
    return buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="도면 분석", layout="wide")
    st.title("도면 업로드 및 AI 분석")

    with st.sidebar:
        api_key = st.text_input("Google Gemini API Key", type="password")
        st.caption("키는 브라우저에만 입력됩니다. 저장되지 않습니다.")
        model_name = "gemini-pro"
        if api_key:
            genai.configure(api_key=api_key)
            try:
                models = list(genai.list_models())
                if not st.session_state.get("models_printed"):
                    print("Available Gemini models:")
                    for model in models:
                        print(model)
                    st.session_state["models_printed"] = True
                model_names = [model.name for model in models if model.name.startswith("models/")]
                if model_names:
                    default_index = 0
                    for idx, name in enumerate(model_names):
                        if name.endswith("gemini-1.5-flash-latest") or name.endswith("gemini-pro"):
                            default_index = idx
                            break
                    model_name = st.selectbox(
                        "분석 모델 선택",
                        model_names,
                        index=default_index,
                    )
            except Exception as exc:
                st.error(f"모델 목록 조회 중 오류가 발생했습니다: {exc}")
        law_pdfs = st.file_uploader(
            "참고 법령 PDF 업로드",
            type=["pdf"],
            accept_multiple_files=True,
        )

    uploaded = st.file_uploader("도면 이미지를 업로드하세요", type=["png", "jpg", "jpeg"])

    left, right = st.columns(2)

    if uploaded is None:
        with left:
            st.info("왼쪽에 도면 이미지가 표시됩니다.")
        with right:
            st.info("오른쪽에 AI 분석 결과가 표시됩니다.")
        return

    image_bytes = uploaded.getvalue()
    image = Image.open(BytesIO(image_bytes))

    with left:
        st.subheader("도면 이미지")
        st.image(image, use_container_width=True)

    with right:
        st.subheader("AI 분석 결과")
        if not api_key:
            st.warning("Google Gemini API Key를 입력하세요.")
        if not law_pdfs:
            st.warning("참고 법령 PDF를 업로드하세요.")

        analyze_clicked = st.button(
            "분석 시작",
            disabled=not api_key or not law_pdfs,
        )

        if analyze_clicked:
            genai.configure(api_key=api_key)
            with st.spinner("분석 중..."):
                try:
                    law_texts: list[str] = []
                    for pdf in law_pdfs:
                        text = extract_pdf_text(pdf.getvalue())
                        if text:
                            law_texts.append(text)
                    law_text = "\n\n---\n\n".join(law_texts).strip()
                    if not law_text:
                        st.error("PDF에서 텍스트를 추출하지 못했습니다.")
                        return
                    result = analyze_floorplan(image, law_text, model_name)
                    st.session_state["analysis_result"] = result
                    st.session_state["analysis_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state["analysis_file"] = uploaded.name
                except Exception as exc:
                    st.error(f"분석 중 오류가 발생했습니다: {exc}")

        if "analysis_result" in st.session_state:
            st.write(st.session_state["analysis_result"])
            font_name, font_path = resolve_korean_font()
            if not font_name:
                st.warning("한글 폰트를 찾지 못했습니다. 기본 폰트로 PDF를 생성합니다.")
            else:
                st.caption(f"PDF 폰트: {font_name} ({font_path})")

            pdf_bytes = build_pdf_bytes(
                analysis_text=st.session_state["analysis_result"],
                plan_filename=st.session_state.get("analysis_file", "unknown.png"),
                analyzed_at=st.session_state.get("analysis_time", "-"),
                font_name=font_name,
            )
            st.download_button(
                "PDF 다운로드",
                data=pdf_bytes,
                file_name="analysis_result.pdf",
                mime="application/pdf",
            )


if __name__ == "__main__":
    main()


