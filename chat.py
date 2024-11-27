import anthropic
import base64
import httpx
import streamlit as st
import PyPDF2
import io
import math
from dotenv import load_dotenv
import os

load_dotenv()

def split_pdf(pdf_file, max_size_mb=32, max_pages=100):
    """Split PDF into chunks based on size and page limits"""
    # Reset file pointer to beginning
    pdf_file.seek(0)
    pdf_bytes = pdf_file.read()
    
    # Debug info
    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    st.write(f"PDF size: {pdf_size_mb:.2f} MB")
    
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(pdf_reader.pages)
    st.write(f"Total pages: {total_pages}")
    
    # If PDF is within limits, return it as a single chunk
    if pdf_size_mb <= max_size_mb and total_pages <= max_pages:
        return [(0, total_pages, pdf_bytes)]
    
    chunks = []
    current_chunk = io.BytesIO()
    chunk_writer = PyPDF2.PdfWriter()
    current_size = 0
    start_page = 0
    
    for i in range(total_pages):
        page = pdf_reader.pages[i]
        temp_writer = PyPDF2.PdfWriter()
        temp_writer.add_page(page)
        temp_bytes = io.BytesIO()
        temp_writer.write(temp_bytes)
        page_size = len(temp_bytes.getvalue())
        
        if current_size + page_size > max_size_mb * 1024 * 1024 or i - start_page >= max_pages:
            # Save current chunk
            chunk_writer.write(current_chunk)
            chunks.append((start_page, i, current_chunk.getvalue()))
            # Start new chunk
            current_chunk = io.BytesIO()
            chunk_writer = PyPDF2.PdfWriter()
            start_page = i
            current_size = 0
            
        chunk_writer.add_page(page)
        current_size += page_size
    
    # Add final chunk
    if current_size > 0:
        chunk_writer.write(current_chunk)
        chunks.append((start_page, total_pages, current_chunk.getvalue()))
    
    return chunks

def chat_with_pdf(pdf_data, user_question):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        st.error("Please set the ANTHROPIC_API_KEY in your .env file")
        return
        
    client = anthropic.Anthropic(api_key=api_key)
    
    # Debug info
    if isinstance(pdf_data, (io.BytesIO, io.StringIO)):
        pdf_data = pdf_data.getvalue()
    
    pdf_size_mb = len(pdf_data) / (1024 * 1024)
    st.write(f"Chunk size being sent to API: {pdf_size_mb:.2f} MB")
    
    try:
        # Verify PDF is valid before sending
        try:
            PyPDF2.PdfReader(io.BytesIO(pdf_data))
        except Exception as e:
            st.error(f"Invalid PDF data: {str(e)}")
            return None
            
        message = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",
            betas=["pdfs-2024-09-25", "prompt-caching-2024-07-31"],
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_data).decode('utf-8')
                            },
                            "cache_control": {
                                "type": "ephemeral"
                            }
                        },
                        {
                            "type": "text",
                            "text": user_question
                        }
                    ]
                }
            ]
        )
        return message.content[0].text
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        if hasattr(e, 'response'):
            st.error(f"API Response: {e.response.text if hasattr(e.response, 'text') else e.response}")
        return None

# Streamlit UI
st.title("PDF Chat with Claude")

uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file is not None:
    try:
        pdf_chunks = split_pdf(uploaded_file)
        
        if len(pdf_chunks) > 1:
            st.write(f"PDF split into {len(pdf_chunks)} chunks")
            selected_chunk = st.selectbox(
                "Select chunk to chat with",
                [f"Pages {chunk[0]+1}-{chunk[1]} (Chunk {i+1})" for i, chunk in enumerate(pdf_chunks)]
            )
            chunk_index = int(selected_chunk.split("Chunk ")[-1].split(")")[0]) - 1
            pdf_data = pdf_chunks[chunk_index][2]
        else:
            pdf_data = pdf_chunks[0][2]

        user_question = st.text_input("Ask a question about the PDF:")
        
        if st.button("Send") and user_question:
            with st.spinner("Claude is thinking..."):
                response = chat_with_pdf(pdf_data, user_question)
                if response:
                    st.write(response)
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
