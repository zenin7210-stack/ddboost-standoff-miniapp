import asyncio
import logging
import json
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '').lstrip('@')
CARDS = {k: os.getenv(k, f'TEST_{k}') for k in ('UZCARD', 'HUMO', 'VISA')}
DB = Path(__file__).with_name('orders.sqlite3')
RANK_IMAGE = Path(__file__).with_name('ranks.webp')
MODES = {'comp': 'Соревновательный', 'duel': 'Дуэль', 'wing': 'Напарники'}
RANKS = ['Калибровка', 'Bronze', 'Silver', 'Gold', 'Phoenix', 'Ranger', 'Champion', 'Master', 'Elite', 'The Legend']
# Price for advancing INTO each next rank; edit these values as needed.
PRICES = [0, 3000, 4000, 6000, 9000, 13000, 18000, 25000, 35000, 50000]
dp = Dispatcher()

class Flow(StatesGroup):
    receipt = State()

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=payload) for label, payload in row] for row in rows])

def single(items):
    return kb([[(label, data)] for label, data in items])

def init_db():
    with sqlite3.connect(DB) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
          access_type TEXT, mode TEXT, current_rank INTEGER, target_rank INTEGER,
          amount INTEGER, card TEXT, receipt_file_id TEXT, receipt_type TEXT,
          status TEXT DEFAULT 'pending', created_at TEXT)''')

def price(start, end, access):
    base = sum(PRICES[start + 1:end + 1])
    return int((Decimal(base) * (Decimal('1.10') if access == 'no' else Decimal('1'))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def fmt(amount):
    return f'{amount:,}'.replace(',', ' ')

def admin_link():
    return f'https://t.me/{ADMIN_USERNAME}' if ADMIN_USERNAME else None

@dp.message(F.web_app_data)
async def receive_webapp_order(message: Message, bot: Bot):
    """Receive a boost order sent by Telegram.WebApp.sendData."""
    try:
        data = json.loads(message.web_app_data.data)
        mode = str(data.get('mode', ''))
        start_name = str(data.get('from', ''))
        end_name = str(data.get('to', ''))
        game_id = str(data.get('gameId', '')).strip()[:80]
        if mode not in MODES or start_name not in RANKS or end_name not in RANKS or not game_id:
            raise ValueError('invalid order fields')
        start, end = RANKS.index(start_name), RANKS.index(end_name)
        if end <= start:
            raise ValueError('target rank must be higher')
        # Mini App displays base rank-step prices; calculate the same amount here,
        # without the legacy +10% login-free checkout surcharge.
        amount = sum(PRICES[start + 1:end + 1])
    except (ValueError, TypeError, json.JSONDecodeError):
        await message.answer('Buyurtma ma’lumotlarini tekshirib, qayta urinib ko‘ring.')
        return

    with sqlite3.connect(DB) as con:
        cur = con.execute(
            '''INSERT INTO orders
               (user_id, username, access_type, mode, current_rank, target_rank,
                amount, card, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (message.from_user.id, message.from_user.username or '', 'no', mode,
             start, end, amount, 'webapp', datetime.now(timezone.utc).isoformat()))
        order_id = cur.lastrowid
    await message.answer(
        f'✅ <b>Buyurtma #{order_id} yuborildi</b>\n🎮 {MODES[mode]}\n'
        f'🏅 {RANKS[start]} → {RANKS[end]}\n🆔 {game_id}\n'
        f'💰 {fmt(amount)} so‘m\n\nTo‘lovni administrator bilan kelishing. '
        'Akkaunt parolingizni botga yubormang.', parse_mode='HTML')
    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            f'🆕 Mini App buyurtma #{order_id}\n👤 {message.from_user.full_name} '
            f'(@{message.from_user.username or "yo‘q"})\n🆔 {message.from_user.id}\n'
            f'🎮 {MODES[mode]}\n🏅 {RANKS[start]} → {RANKS[end]}\n'
            f'🎯 Game ID/nick: {game_id}\n💰 {fmt(amount)} so‘m\n⚠️ To‘lovni alohida tasdiqlang.',
            reply_markup=single([('✅ Tasdiqlash', f'approve:{order_id}'),
                                 ('❌ Rad etish', f'reject:{order_id}')]))

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('🔷 <b>DD BOOST SO2</b>\n\nXush kelibsiz! Boost turini tanlang:',
        parse_mode='HTML', reply_markup=single([('🔐 Akkauntga kirish orqali', 'access:yes'), ('🎮 Akkauntga kirmasdan (+10%)', 'access:no')]))

@dp.callback_query(F.data.startswith('access:'))
async def access_choice(call: CallbackQuery, state: FSMContext):
    await state.update_data(access=call.data.split(':')[1])
    await call.message.edit_text('🎮 Boost rejimini tanlang:', reply_markup=single([(v, 'mode:' + k) for k, v in MODES.items()]))
    await call.answer()

@dp.callback_query(F.data.startswith('mode:'))
async def mode_choice(call: CallbackQuery, state: FSMContext):
    mode = call.data.split(':')[1]
    if mode not in MODES:
        return await call.answer('Noto‘g‘ri rejim', show_alert=True)
    await state.update_data(mode=mode)
    await call.message.delete()
    await call.message.answer_photo(FSInputFile(RANK_IMAGE), caption='🏆 DD BOOST SO2\n\n📊 Hozirgi rangingizni tanlang:', reply_markup=single([(r, f'from:{i}') for i, r in enumerate(RANKS[:-1])] + [('⬅️ Orqaga', 'back:modes')]))
    await call.answer()

@dp.callback_query(F.data.startswith('from:'))
async def from_choice(call: CallbackQuery, state: FSMContext):
    i = int(call.data.split(':')[1])
    if not 0 <= i < len(RANKS)-1:
        return await call.answer('Noto‘g‘ri rang', show_alert=True)
    await state.update_data(start=i)
    await call.message.edit_caption(caption=f'🏆 DD BOOST SO2\n\n📊 Hozirgi rang: {RANKS[i]}\n🎯 Qaysi rangga chiqmoqchisiz?', reply_markup=single([(RANKS[j], f'to:{j}') for j in range(i + 1, len(RANKS))] + [('⬅️ Orqaga', 'back:from')]))
    await call.answer()

@dp.callback_query(F.data.startswith('to:'))
async def to_choice(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if not {'start', 'mode', 'access'} <= d.keys():
        return await call.answer('Qaytadan /start bosing', show_alert=True)
    end = int(call.data.split(':')[1])
    if not d['start'] < end < len(RANKS):
        return await call.answer('Noto‘g‘ri rang', show_alert=True)
    amount = price(d['start'], end, d['access'])
    await state.update_data(end=end, amount=amount)
    access_text = 'Akkauntga kirish orqali' if d['access'] == 'yes' else 'Akkauntga kirmasdan (+10%)'
    await call.message.delete()
    await call.message.answer(
        f'🔷 <b>DD BOOST SO2</b>\n\n🎮 Rejim: {MODES[d["mode"]]}\n🔐 Boost turi: {access_text}\n'
        f'📊 Hozirgi rang: {RANKS[d["start"]]}\n🏆 Kerakli rang: {RANKS[end]}\n\n💰 <b>Narx: {fmt(amount)} so‘m</b>',
        parse_mode='HTML', reply_markup=single([('💳 To‘lov qilish', 'pay')]))
    await call.answer()


@dp.callback_query(F.data.startswith('back:'))
async def go_back(call: CallbackQuery, state: FSMContext):
    step = call.data.split(':', 1)[1]
    if step == 'modes':
        await call.message.delete()
        await call.message.answer('🎮 Boost rejimini tanlang:', reply_markup=single([(v, 'mode:' + k) for k, v in MODES.items()]))
    elif step == 'from':
        await call.message.edit_caption(caption='🏆 DD BOOST SO2\n\n📊 Hozirgi rangingizni tanlang:', reply_markup=single([(r, f'from:{i}') for i, r in enumerate(RANKS[:-1])] + [('⬅️ Orqaga', 'back:modes')]))
    await call.answer()

@dp.callback_query(F.data == 'pay')
async def pay_choice(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if 'amount' not in d:
        return await call.answer('Qaytadan /start bosing', show_alert=True)
    await call.message.edit_text('💳 To‘lov usulini tanlang:', reply_markup=single([(k, f'card:{k}') for k in CARDS]))
    await call.answer()

@dp.callback_query(F.data.startswith('card:'))
async def card_choice(call: CallbackQuery, state: FSMContext):
    card = call.data.split(':')[1]
    d = await state.get_data()
    if card not in CARDS or 'amount' not in d:
        return await call.answer('Qaytadan /start bosing', show_alert=True)
    await state.update_data(card=card)
    await state.set_state(Flow.receipt)
    await call.message.edit_text(
        f'💳 <b>{card}</b>\nRekvizit: <code>{CARDS[card]}</code>\n'
        f'💰 Summa: <b>{fmt(d["amount"])} so‘m</b>\n\n'
        '⚠️ Test rekvizitlar bo‘lsa, pul yubormang.\n'
        'To‘lovdan so‘ng chek rasmini yoki faylini shu yerga yuboring.', parse_mode='HTML')
    await call.answer()

@dp.message(Flow.receipt, F.photo | F.document)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    d = await state.get_data()
    if not {'access', 'mode', 'start', 'end', 'amount', 'card'} <= d.keys():
        await state.clear()
        return await message.answer('Qaytadan /start bosing.')
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_type = 'photo' if message.photo else 'document'
    with sqlite3.connect(DB) as con:
        cur = con.execute('''INSERT INTO orders
          (user_id, username, access_type, mode, current_rank, target_rank, amount, card, receipt_file_id, receipt_type, created_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
          (message.from_user.id, message.from_user.username or '', d['access'], d['mode'], d['start'], d['end'], d['amount'], d['card'], file_id, file_type, datetime.now(timezone.utc).isoformat()))
        order_id = cur.lastrowid
    await state.clear()
    await message.answer(f'✅ <b>Buyurtmangiz #{order_id} qabul qilindi!</b>\nTo‘lov tekshirilgach, administrator siz bilan bog‘lanadi.\n\n/start — yangi buyurtma', parse_mode='HTML')
    if ADMIN_ID:
        try:
            txt = (f'🆕 Buyurtma #{order_id}\n👤 User: {message.from_user.full_name} (@{message.from_user.username or "yoq"})\n'
                   f'🆔 ID: {message.from_user.id}\n🎮 {MODES[d["mode"]]}\n🔐 {"Kirish bilan" if d["access"] == "yes" else "Kirishsiz"}\n'
                   f'🏆 {RANKS[d["start"]]} → {RANKS[d["end"]]}\n💰 {fmt(d["amount"])} so‘m\n💳 {d["card"]}')
            await bot.send_message(ADMIN_ID, txt, reply_markup=single([('✅ Tasdiqlash', f'approve:{order_id}'), ('❌ Rad etish', f'reject:{order_id}')]))
            await message.copy_to(ADMIN_ID)
        except Exception:
            logging.exception('Failed to notify admin')

@dp.message(Flow.receipt)
async def wrong_receipt(message: Message):
    await message.answer('📷 Iltimos, to‘lov chekini rasm yoki fayl sifatida yuboring.')

@dp.callback_query(F.data.startswith(('approve:', 'reject:')))
async def admin_action(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        return await call.answer('Ruxsat yo‘q', show_alert=True)
    action, id_str = call.data.split(':', 1)
    order_id = int(id_str)
    with sqlite3.connect(DB) as con:
        row = con.execute('SELECT user_id, access_type, status FROM orders WHERE id=?', (order_id,)).fetchone()
        if not row or row[2] != 'pending':
            return await call.answer('Buyurtma allaqachon ko‘rib chiqilgan', show_alert=True)
        con.execute('UPDATE orders SET status=? WHERE id=?', ('approved' if action == 'approve' else 'rejected', order_id))
    if action == 'approve':
        info = ('Akkaunt ma’lumotlarini faqat administrator bilan shaxsiy chatda kelishing.' if row[1] == 'yes'
                else 'Administrator siz bilan bog‘lanib, birgalikda boost vaqtini kelishadi.')
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='👤 Administrator', url=admin_link())]]) if admin_link() else None
        await bot.send_message(row[0], f'✅ Buyurtma #{order_id} tasdiqlandi!\n{info}', reply_markup=markup)
    else:
        await bot.send_message(row[0], f'❌ Buyurtma #{order_id} tasdiqlanmadi. Administratorga murojaat qiling.')
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer('Saqlandi')

@dp.message(Command('admin'))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    with sqlite3.connect(DB) as con:
        total = con.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        approved = con.execute("SELECT COUNT(*) FROM orders WHERE status='approved'").fetchone()[0]
        rows = con.execute('SELECT id, amount, status FROM orders ORDER BY id DESC LIMIT 10').fetchall()
    report = '\n'.join(f'#{i} — {fmt(amount)} so‘m — {status}' for i, amount, status in rows) or 'Hozircha buyurtmalar yo‘q.'
    await message.answer(f'⚙️ DD BOOST SO2\nJami: {total} | Kutilmoqda: {pending} | Tasdiqlangan: {approved}\n\nSo‘nggi buyurtmalar:\n{report}')

async def main():
    if not TOKEN or TOKEN == 'PASTE_BOTFATHER_TOKEN_HERE':
        raise RuntimeError('Set BOT_TOKEN in .env first')
    init_db()
    bot = Bot(TOKEN)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
