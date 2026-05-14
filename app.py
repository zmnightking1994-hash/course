import streamlit as st 
import google.genai as genai
import json
from sqlalchemy import Numeric, create_engine, Table, Column, Integer, String, Text, MetaData, insert, select, UniqueConstraint
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime

# --- إعدادات قاعدة البيانات ---
DB_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DB_URL)
metadata = MetaData()

answers_table = Table(
    "student_submissions", metadata,
    Column("id", Integer, primary_key=True),
    Column("student_name", String),
    Column("question_id", String),
    Column("answer_text", Text),
    Column("ai_score", Numeric(5, 2)),
    Column("submission_time", String),
    UniqueConstraint('student_name', 'question_id', name='uix_student_question')
)

# --- دالة التحقق من الـ AI ---
def check_ai_content(text):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    prompt = f"""Analyze if this text is AI-generated. Return ONLY a valid JSON: {{"score": 85}}. Text: {text}"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return float(json.loads(clean_json).get("score", 0))
    except:
        return 0.0

# ==========================================
# --- تحديد الواجهة بناءً على الرابط ---
# ==========================================
role = st.query_params.get("role", "student")

if role == "teacher":
    # ==========================================
    # واجهة المدرس (لوحة التحكم)
    # ==========================================
    st.title("👨‍🏫 لوحة تحكم المدرس")
    st.markdown("مرحباً بك. يمكنك هنا متابعة إجابات الطلاب ونسب الـ AI.")
    
    with engine.connect() as conn:
        # جلب جميع البيانات مرتبة من الأحدث للأقدم
        stmt = select(answers_table).order_by(answers_table.c.id.desc())
        data = conn.execute(stmt).fetchall()
        
    if not data:
        st.info("لا توجد إجابات مسجلة حتى الآن.")
    else:
        # تحويل البيانات إلى DataFrame (جدول باندا)
        df = pd.DataFrame(data, columns=["الرقم", "اسم الطالب", "رقم السؤال", "الإجابة", "نسبة AI %", "وقت التسليم"])
        
        # إضافة عمود حالة الاشتباه لتلوين الجدول
        def get_status(score):
            if score >= 70: return "⚠️ اشتباه عالي"
            elif score >= 40: return "🟡 متوسط"
            else: return "✅ آمن"
            
        df["الحالة"] = df["نسبة AI %"].apply(get_status)
        
        # فلاتر جانبية
        st.sidebar.header("فلاتر البحث")
        search_name = st.sidebar.text_input("بحث باسم الطالب:")
        search_q = st.sidebar.selectbox("فلترة حسب السؤال:", ["الكل"] + df["رقم السؤال"].unique().tolist())
        
        # تطبيق الفلاتر
        if search_name:
            df = df[df["اسم الطالب"].str.contains(search_name, case=False)]
        if search_q != "الكل":
            df = df[df["رقم السؤال"] == search_q]
            
        # عرض الجدول
        st.dataframe(
            df[["اسم الطالب", "رقم السؤال", "نسبة AI %", "الحالة", "وقت التسليم"]], 
            use_container_width=True,
            hide_index=True
        )
        
        # زر لتحميل التقرير كملف Excel/CSV
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 تحميل التقرير الكامل (CSV)",
            data=csv,
            file_name=f'teacher_report_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv'
        )
        
        # عرض إجابة طالب محددة عند الضغط عليها
        st.markdown("---")
        st.subheader("تفاصيل إجابة طالب")
        selected_student = st.selectbox("اختر طالب لرؤية إجابته كاملة:", df["اسم الطالب"].unique())
        
        student_data = df[df["اسم الطالب"] == selected_student].iloc[0]
        st.info(f"**الطالب:** {student_data['اسم الطالب']}\n\n**السؤال:** {student_data['رقم السؤال']}\n\n**نسبة الـ AI:** {student_data['نسبة AI %']}%\n\n**الإجابة:**\n{student_data['الإجابة']}")

else:
        # ==========================================
    # واجهة الطالب
    # ==========================================
    st.title("📝 نظام استلام الإجابات")

    name = st.text_input("اسم الطالب")
    q_id = st.query_params.get("qid", "Default_Q")

    student_ans = st.text_area("اكتب إجابتك هنا بيدك:", height=200, key="answer_box")

    # ==========================================
    # كود منع اللصق القوي (لابتوب + جوال)
    # ==========================================
    from streamlit_js_eval import streamlit_js_eval

    # هذا الكود يتم حقنه في الصفحة الرئيسية وليس في إطار مخفي
    js_block_paste = """
    function blockPaste() {
        // البحث عن حقول النص في الصفحة
        const textareas = document.querySelectorAll('textarea');
        textareas.forEach(area => {
            // وضع علامة لتجنب تكرار الحدث
            if (!area.dataset.pasteBlocked) {
                area.dataset.pasteBlocked = 'true';
                // استخدام capture phase لضمان التغلب على Streamlit
                area.addEventListener('paste', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    alert('⚠️ عذراً، النسخ واللصق ممنوع!');
                    return false;
                }, true); 
            }
        });
    }

    // التشغيل الأولي
    blockPaste();

    // مراقبة إعادة رسم الصفحة (Streamlit يعيد الرسم باستمرار)
    if (!window._pasteObserverStarted) {
        window._pasteObserverStarted = true;
        const observer = new MutationObserver(blockPaste);
        observer.observe(document.body, { childList: true, subtree: true });
    }
    """
    
    # تشغيل الكود بصمت
    streamlit_js_eval(js_expressions=js_block_paste, desired_output_type="ignore", key="paste_blocker")



    if st.button("إرسال الإجابة"):
        if not name or not student_ans.strip():
            st.error("يرجى ملء الاسم وكتابة الإجابة.") 
        else:
            with st.spinner("جاري التحقق والتحليل..."):
                try:
                    with engine.connect() as conn:
                        # التحقق من التكرار
                        check_stmt = select(answers_table).where(
                            (answers_table.c.student_name == name) &
                            (answers_table.c.question_id == q_id)
                        )
                        if conn.execute(check_stmt).fetchone():
                            st.error("❌ لقد قمت بتسليم إجابة لهذا السؤال مسبقاً!")
                        else:
                            # التحليل والحفظ
                            score = check_ai_content(student_ans)
                            stmt = insert(answers_table).values(
                                student_name=name, question_id=q_id,
                                answer_text=student_ans, ai_score=score,
                                submission_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            )
                            conn.execute(stmt)
                            conn.commit()
                            
                            if score > 70: st.warning(f"تم الاستلام يا {name}، نسبة الاشتباه مرتفعة: {score}%")
                            else: st.success(f"تم الاستلام بنجاح يا {name}. نسبة الشك: {score}%")
                except Exception as e:
                    st.error(f"حدث خطأ: {e}")
