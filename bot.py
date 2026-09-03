import os
import re
import json
from datetime import datetime, date, timedelta
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)


# ==========================================================
# الإعدادات المهمة
# ==========================================================

# ضع التوكن الجديد من @BotFather هنا بعد تنفيذ /revoke
TOKEN = "8372904725:AAF9CSyLo53DOHzwzcnwnXI2B5MHdKVBCV4"

# ID لملف Google Sheets
SPREADSHEET_ID = "1Tt59ai-q3fYu_E1YmhH_tW3eK-uRaJePB0xYcu8fuQA"

# اسم تبويب الورقة أسفل Google Sheets
WORKSHEET_NAME = "توريدات"

# الحسابات المسموح لها باستخدام البوت
ALLOWED_CHAT_IDS = {
    8970598966,
}

# عمود التاريخ في الشيت
DATE_COLUMN_LETTER = "B"

# أول صف فعلي للبيانات
START_ROW = 6


# ==========================================================
# لا تعدّل عادةً ما بعد هذه المنطقة
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"

LOCATION, AMOUNT = range(2)

# أسماء الأماكن وأرقام الأعمدة المقابلة لها
PLACES_MAPPING = {
    "الاكاديميه": 3,
    "مصر الجديدة": 4,
    "التكنولوجية": 5,
    "معهد ضباط الصف": 6,
    "المشاه": 7,
    "المدرعات": 8,
    "المدفعية": 9,
    "المركبات": 10,
    "اسلحه": 11,
    "كيما": 12,
    "امداد وتموين 1": 13,
    "امداد وتموين 3": 14,
    "مهن مركبات ومدرعات": 15,
    "مهن اشاره": 16,
    "كلية ضباط احتياط": 17,
    "مركز كسفريت": 18,
}


def main():
    """تشغيل البوت."""

    if not TOKEN:
        print("خطأ: TELEGRAM_TOKEN غير موجود.")
        return

    application = Application.builder().token(TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler(["start", "add"], start),
        ],
        states={
            LOCATION: [
                CallbackQueryHandler(receive_location),
            ],
            AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_amount,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(conversation_handler)

    print("البوت يعمل الآن باستخدام Google Sheets...")
    print("اضغط Ctrl+C للإيقاف.")

    application.run_polling()


if __name__ == "__main__":
    main()


def normalize_date_value(value):
    """
    يحول التاريخ الموجود داخل Google Sheets إلى date.

    يدعم مثلًا:
    2026/09/04
    2026-09-04
    04/09/2026
    4/9/2026
    4-سبتمبر
    4 سبتمبر
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    if not value:
        return None

    # إزالة المسافات وتوحيد أشكال الشرطات
    value = value.replace(" ", "")
    value = value.replace("ـ", "")
    value = value.replace("–", "-")
    value = value.replace("—", "-")

    # دعم صيغ التاريخ الرقمية
    numeric_value = value.replace("-", "/").replace(".", "/")

    numeric_formats = [
        "%Y/%m/%d",
        "%Y/%m/%d%H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%m/%d/%Y",
        "%m/%d/%y",
    ]

    for date_format in numeric_formats:
        try:
            return datetime.strptime(
                numeric_value,
                date_format,
            ).date()
        except ValueError:
            continue

    # دعم رقم التاريخ التسلسلي في Google Sheets إن ظهر
    try:
        serial_number = float(value)
        google_sheets_epoch = date(1899, 12, 30)

        return google_sheets_epoch + timedelta(
            days=int(serial_number)
        )
    except (ValueError, OverflowError):
        pass

    # دعم أسماء الشهور العربية الموجودة داخل جدولك
    arabic_months = {
        "يناير": 1,
        "فبراير": 2,
        "مارس": 3,
        "أبريل": 4,
        "ابريل": 4,
        "مايو": 5,
        "يونيو": 6,
        "يوليو": 7,
        "أغسطس": 8,
        "اغسطس": 8,
        "سبتمبر": 9,
        "أكتوبر": 10,
        "اكتوبر": 10,
        "نوفمبر": 11,
        "ديسمبر": 12,
    }

    # مثال: "4-سبتمبر" أو "4سبتمبر"
    for month_name, month_number in arabic_months.items():
        if value.endswith(month_name):
            day_text = value[:-len(month_name)]
            day_text = day_text.replace("-", "").strip()

            if day_text.isdigit():
                day_number = int(day_text)

                try:
                    # الجدول الحالي خاص بسنة اليوم الحالية
                    return date(
                        date.today().year,
                        month_number,
                        day_number,
                    )
                except ValueError:
                    return None

    return None


def column_number_to_letter(column_number):
    """تحويل رقم العمود إلى حرف: 3 تصبح C، و18 تصبح R."""

    result = ""

    while column_number > 0:
        column_number, remainder = divmod(
            column_number - 1,
            26,
        )
        result = chr(65 + remainder) + result

    return result


def is_valid_amount(value):
    """يتحقق أن المبلغ رقم موجب أو صفر."""

    value = value.strip().replace(",", ".")

    return bool(re.fullmatch(r"\d+(\.\d+)?", value))


def convert_amount(value):
    """تحويل نص المبلغ إلى رقم صحيح أو عشري."""

    value = value.strip().replace(",", ".")

    if "." in value:
        return float(value)

    return int(value)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """بداية العملية بأمر /start أو /add."""

    chat_id = update.effective_chat.id

    if chat_id not in ALLOWED_CHAT_IDS:
        await update.effective_message.reply_text(
            "⛔ غير مصرح لك باستخدام هذا البوت."
        )
        return ConversationHandler.END

    keyboard = []
    row = []

    for place in PLACES_MAPPING:
        row.append(
            InlineKeyboardButton(
                text=place,
                callback_data=place,
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    await update.effective_message.reply_text(
        "اختر المكان لتسجيل مبلغ اليوم:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return LOCATION


async def receive_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """يحفظ المكان المختار ثم يطلب إدخال المبلغ."""

    query = update.callback_query
    await query.answer()

    context.user_data["location"] = query.data

    await query.edit_message_text(
        f"📌 تم اختيار: {query.data}\n\n"
        "أرسل المبلغ الآن.\n"
        "مثال: 1500"
    )

    return AMOUNT


async def receive_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """يجد صف اليوم الموجود مسبقًا، ثم يسجل المبلغ في عمود المكان."""

    amount_text = update.effective_message.text.strip()

    if not is_valid_amount(amount_text):
        await update.effective_message.reply_text(
            "❌ أرسل مبلغًا رقميًا فقط.\n"
            "مثال: 1500 أو 125.5"
        )
        return AMOUNT

    location = context.user_data.get("location")

    if location not in PLACES_MAPPING:
        await update.effective_message.reply_text(
            "❌ حدثت مشكلة في اختيار المكان.\n"
            "ابدأ من جديد باستخدام /add."
        )
        context.user_data.clear()
        return ConversationHandler.END

    amount = convert_amount(amount_text)
    today = date.today()

    try:
        worksheet = connect_to_sheet()

        # قراءة عمود B كما هو ظاهر في Google Sheets
        date_values = worksheet.get(
            f"{DATE_COLUMN_LETTER}{START_ROW}:{DATE_COLUMN_LETTER}",
            value_render_option="FORMATTED_VALUE",
        )

        target_row = None

        for index, row_values in enumerate(date_values):
            if not row_values:
                continue

            displayed_date = str(row_values[0]).strip()
            sheet_date = normalize_date_value(displayed_date)

            if sheet_date == today:
                target_row = START_ROW + index
                break

        # الجدول عندك يحتوي على صفوف كل الأيام بالفعل:
        # هنا لا نضيف صفًا جديدًا، فقط نوضح إن البحث لم يجد الصف.
        if target_row is None:
            await update.effective_message.reply_text(
                "❌ لم أجد صف تاريخ اليوم داخل العمود B.\n\n"
                f"التاريخ المطلوب: "
                f"{today.strftime('%d-%m-%Y')}\n\n"
                "البوت يفهم صيغ مثل:\n"
                "4-سبتمبر\n"
                "4 سبتمبر\n"
                "2026/09/04\n\n"
                "تأكد أن صف اليوم موجود في العمود B."
            )
            context.user_data.clear()
            return ConversationHandler.END

        column_number = PLACES_MAPPING[location]
        column_letter = column_number_to_letter(column_number)
        cell_address = f"{column_letter}{target_row}"

        # تسجيل المبلغ كرقم حقيقي داخل Google Sheets
        worksheet.update(
            range_name=cell_address,
            values=[[amount]],
            value_input_option="USER_ENTERED",
        )

        await update.effective_message.reply_text(
            "✅ تم الحفظ بنجاح!\n\n"
            f"📅 التاريخ: {today.strftime('%d-%m-%Y')}\n"
            f"📍 المكان: {location}\n"
            f"💰 المبلغ: {amount}\n"
            f"📌 تم التسجيل في الخلية: {cell_address}"
        )

    except gspread.exceptions.SpreadsheetNotFound:
        await update.effective_message.reply_text(
            "❌ لم أجد ملف Google Sheet.\n\n"
            "راجع Spreadsheet ID وتأكد أن الشيت تمت مشاركته "
            "مع Service Account بصلاحية Editor."
        )

    except gspread.exceptions.WorksheetNotFound:
        await update.effective_message.reply_text(
            f"❌ لم أجد تبويبًا باسم: {WORKSHEET_NAME}\n\n"
            "راجع اسم تبويب الورقة أسفل Google Sheets."
        )

    except FileNotFoundError:
        await update.effective_message.reply_text(
            "❌ لم أجد ملف credentials.json.\n\n"
            "تأكد أنه في نفس مجلد bot.py وأن اسمه بالضبط "
            "credentials.json."
        )

    except PermissionError:
        await update.effective_message.reply_text(
            "❌ حساب Google Service Account لا يملك صلاحية تعديل الشيت.\n\n"
            "افتح مشاركة Google Sheet وأضف حساب الخدمة بصلاحية Editor."
        )

    except Exception as error:
        print(f"ERROR: {repr(error)}")

        await update.effective_message.reply_text(
            "❌ حدث خطأ أثناء الاتصال بـ Google Sheets.\n"
            "راجع PowerShell لمعرفة تفاصيل الخطأ."
        )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """إلغاء العملية الحالية."""

    context.user_data.clear()

    await update.effective_message.reply_text(
        "تم إلغاء العملية."
    )

    return ConversationHandler.END


def main():
    """تشغيل البوت."""

    if not TOKEN:
        print("خطأ: TELEGRAM_TOKEN غير موجود.")
    return
    print(
            "خطأ: ضع Telegram Token الجديد في متغير TOKEN داخل bot.py."
        )
    return

    application = Application.builder().token(TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler(["start", "add"], start),
        ],
        states={
            LOCATION: [
                CallbackQueryHandler(receive_location),
            ],
            AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_amount,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(conversation_handler)

    print("البوت يعمل الآن باستخدام Google Sheets...")
    print("اضغط Ctrl+C للإيقاف.")

    application.run_polling()


if __name__ == "__main__":
    main()