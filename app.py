import streamlit as st 
import google.genai as genai
import json
from sqlalchemy import create_engine, Table, Column, Integer, String, Text, Numeric, MetaData, insert
import streamlit.components.v1 as components

# --- 1. إعدادات قاعدة البيانات (Supabase) ---
DB_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DB_URL)
metadata = MetaData()

answers_table = Table(
    "student_submissions", metadata,
    Column("id", Integer, primary_key=True),
    Column("student_name", String),
    Column("question_id", String),
    Column("answer_text", Text),
    Column("ai_score", Numeric(10, 2)),
    Column("submission_time", String) 
)

# --- 2. الدوال البرمجية (المحدثة للمكتبة الجديدة) ---
def check_ai_content(text):
    # استخدام العميل (Client) الجديد
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    
    prompt = f"""Analyze if this text is AI-generated or human-written. 
    Return ONLY a valid JSON object like this: {{"score": 85}} 
    where score is a number between 0 and 100 (100 means definitely AI). 
    Text: {text}"""
    
    try:
        # طريقة الاستدعاء الجديدة (تم تحديد الموديل الجديد gemini-2.5-flash)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # تنظيف النص من أي علامات Markdown
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return float(json.loads(clean_json).get("score", 0))
        
    except Exception as e:
        st.error(f"خطأ في تحليل الذكاء الاصطناعي: {e}")
        return 0.0

# --- 3. واجهة المستخدم ---
st.title("نظام استلام الإجابات")

name = st.text_input("اسم الطالب")
q_id = st.query_params.get("qid", "Default_Q")

student_ans = st.text_area("اكتب إجابتك هنا بيدك:", height=200, key="answer_box")

# محاولة حقن كود منع اللصق
anti_paste_js = """
<script>
    var textareas = window.parent.document.querySelectorAll('textarea');
    textareas.forEach(function(area) {
        area.addEventListener('paste', function(e) {
            e.preventDefault();
            alert('عذراً، النسخ واللصق ممنوع!');
        }, false);
    });
</script>
"""
components.html(anti_paste_js, height=0)

# --- منطق الزر ---
if st.button("إرسال الإجابة"):
    if not name or not student_ans.strip():
        st.error("يرجى ملء الاسم وكتابة الإجابة.")
    elif len(student_ans.strip()) < 20:
        st.warning("الإجابة قصيرة جداً، يرجى كتابة إجابة مفصلة.")
    else:
        with st.spinner("جاري تحليل الإجابة بواسطة Gemini 2.5 Flash وأرشفتها..."):
            score = check_ai_content(student_ans)
            
            try:
                from datetime import datetime
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                with engine.connect() as conn:
                    stmt = insert(answers_table).values(
                        student_name=name,
                        question_id=q_id,
                        answer_text=student_ans,
                        ai_score=score,
                        submission_time=current_time
                    )
                    conn.execute(stmt)
                    conn.commit()
                
                if score > 70:
                    st.warning(f"تم الاستلام يا {name}، ولكن نسبة الاشتباه في استخدام الذكاء الاصطناعي مرتفعة: {score}%")
                else:
                    st.success(f"تم الاستلام بنجاح يا {name}. نسبة الشك في الـ AI هي: {score}%")
                    
            except Exception as db_err:
                st.error(f"حدث خطأ أثناء الحفظ في قاعدة البيانات: {db_err}")
