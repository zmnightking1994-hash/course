import streamlit as st 
import google.genai as genai
import json
from sqlalchemy import Numeric, create_engine, Table, Column, Integer, String, Text, MetaData, insert, select, UniqueConstraint
import pandas as pd
from datetime import datetime
import time
from streamlit_js_eval import streamlit_js_eval

# --- 1. إعدادات قاعدة البيانات ---
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

# --- 2. دالة التحقق من الـ AI ---
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
# --- 3. تحديد الواجهة بناءً على الرابط ---
# ==========================================
role = st.query_params.get("role", "student")

# ==========================================
# واجهة المدرس (لوحة التحكم)
# ==========================================
if role == "teacher":
    st.title("👨‍🏫 لوحة تحكم المدرس")
    
    # كلمة سر المدرس
    TEACHER_PASSWORD = "admin123"
    pwd = st.text_input("أدخل كلمة سر المدرس:", type="password")
    
    if pwd != TEACHER_PASSWORD:
        st.error("كلمة السر خاطئة. ليس لديك صلاحية الدخول.")
        st.stop()
    else:
        st.success("تم تسجيل الدخول بنجاح")
        st.markdown("يمكنك هنا متابعة إجابات الطلاب ونسب الـ AI.")
        
        with engine.connect() as conn:
            stmt = select(answers_table).order_by(answers_table.c.id.desc())
            data = conn.execute(stmt).fetchall()
            
        if not data:
            st.info("لا توجد إجابات مسجلة حتى الآن.")
        else:
            df = pd.DataFrame(data, columns=["الرقم", "اسم الطالب", "رقم السؤال", "الإجابة", "نسبة AI %", "وقت التسليم"])
            
            def get_status(score):
                if score >= 70: return "⚠️ اشتباه عالي"
                elif score >= 40: return "🟡 متوسط"
                else: return "✅ آمن"
                
            df["الحالة"] = df["نسبة AI %"].apply(get_status)
            
            st.sidebar.header("فلاتر البحث")
            search_name = st.sidebar.text_input("بحث باسم الطالب:")
            search_q = st.sidebar.selectbox("فلترة حسب السؤال:", ["الكل"] + df["رقم السؤال"].unique().tolist())
            
            if search_name:
                df = df[df["اسم الطالب"].str.contains(search_name, case=False)]
            if search_q != "الكل":
                df = df[df["رقم السؤال"] == search_q]
                
            st.dataframe(
                df[["اسم الطالب", "رقم السؤال", "نسبة AI %", "الحالة", "وقت التسليم"]], 
                use_container_width=True,
                hide_index=True
            )
            
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 تحميل التقرير الكامل (CSV)",
                data=csv,
                file_name=f'teacher_report_{datetime.now().strftime("%Y%m%d")}.csv',
                mime='text/csv'
            )
            
            st.markdown("---")
            st.subheader("تفاصيل إجابة طالب")
            selected_student = st.selectbox("اختر طالب لرؤية إجابته كاملة:", df["اسم الطالب"].unique())
            
            student_data = df[df["اسم الطالب"] == selected_student].iloc[0]
            st.info(f"**الطالب:** {student_data['اسم الطالب']}\n\n**السؤال:** {student_data['رقم السؤال']}\n\n**نسبة الـ AI:** {student_data['نسبة AI %']}%\n\n**الإجابة:**\n{student_data['الإجابة']}")

# ==========================================
# واجهة الطالب
# ==========================================
else:
    st.title("📝 نظام استلام الإجابات")

    name = st.text_input("اسم الطالب")
    q_id = st.query_params.get("qid", "Default_Q")

    student_ans = st.text_area("اكتب إجابتك هنا بيدك:", height=200, key="answer_box")

    # كود منع اللصق النووي
    nuke_paste_js = """
    (function() {
        function attachBlocker() {
            const areas = document.querySelectorAll('textarea');
            areas.forEach(area => {
                if (!area.dataset.nukeApplied) {
                    area.dataset.nukeApplied = 'true';
                    let lastLen = area.value.length;

                    area.addEventListener('beforeinput', function(e) {
                        if (e.inputType === 'insertFromPaste') {
                            e.preventDefault();
                            alert('❌ اللصق ممنوع!');
                            return false;
                        }
                    }, true);

                    area.addEventListener('input', function(e) {
                        let currentLen = area.value.length;
                        if (currentLen - lastLen > 5) {
                            area.value = area.value.substring(0, lastLen);
                            alert('❌ تم اكتشاف لصق! تم حذف النص.');
                        }
                        lastLen = currentLen;
                    }, true);
                }
            });
        }

        attachBlocker();
        
        if (!window._nukeObserver) {
            window._nukeObserver = new MutationObserver(attachBlocker);
            window._nukeObserver.observe(document.body, { childList: true, subtree: true, attributes: true });
        }
    })();
    """
    
    streamlit_js_eval(js_expressions=nuke_paste_js, desired_output_type="ignore", key="nuke_paste")

    # تسجيل وقت الدخول لحساب سرعة الكتابة
    if "page_load_time" not in st.session_state:
        st.session_state.page_load_time = time.time()

    # منطق زر الإرسال
    if st.button("إرسال الإجابة"):
        if not name or not student_ans.strip():
            st.error("يرجى ملء الاسم وكتابة الإجابة.") 
        else:
            # كشف اللصق من السيرفر (حساب السرعة)
            time_taken = time.time() - st.session_state.page_load_time
            typing_speed = len(student_ans) / time_taken
            
            if typing_speed > 40 and len(student_ans) > 50:
                st.error("❌ تم اكتشاف محاولة لصق نص بسرعة غير طبيعية! يرجى الكتابة بيدك.")
                st.session_state.page_load_time = time.time()
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
                                
                                if score > 70: 
                                    st.warning(f"تم الاستلام يا {name}، نسبة الاشتباه مرتفعة: {score}%")
                                else: 
                                    st.success(f"تم الاستلام بنجاح يا {name}. نسبة الشك: {score}%")
                                
                                # إعادة ضبط الوقت
                                st.session_state.page_load_time = time.time()
                                    
                    except Exception as e:
                        st.error(f"حدث خطأ: {e}")
