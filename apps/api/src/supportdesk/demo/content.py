"""Demo knowledge for "Lumen", a made-up smart lighting company (hardware plus an app)."""

from __future__ import annotations

GUIDE_MD = """# Lumen Help Guide

## Setting up your first Lumen bulb

Screw the bulb in and switch the lamp on. The bulb blinks blue when it is ready to pair.
Open the Lumen app, tap Add device, and follow the steps. Pairing takes about a minute.
Keep your phone within 5 metres of the bulb while it pairs.

## The bulb will not pair

Most pairing problems are the Wi-Fi band. Lumen bulbs use 2.4 GHz Wi-Fi only; if your
router combines 2.4 and 5 GHz under one name, turn on the router's 2.4 GHz compatibility
mode or create a separate 2.4 GHz network for setup.

To reset a bulb, switch it off and on five times, waiting one second between each. The
bulb flashes white three times when the reset worked, then blinks blue, ready to pair again.

## Lumen Bridge

The Lumen Bridge connects up to 50 bulbs and keeps schedules running when your internet is
down. Plug it into your router with the included cable. The light on the Bridge turns solid
green when it is online. The Bridge is required for more than 10 bulbs in one home.

## Firmware updates

Bulbs and the Bridge update themselves overnight between 2 and 4 am local time. You can
start an update now in the app under Settings, Devices, Check for updates. Do not switch
the light off during an update; it takes about three minutes.

## Schedules and scenes

Scenes save the colour and brightness of several lights at once. Schedules run scenes at
set times or at sunrise and sunset. Schedules run on the Bridge, so they keep working when
your phone is off. Without a Bridge, schedules need the bulb to stay connected to Wi-Fi.

## Voice assistants

Lumen works with Amazon Alexa and Google Home. In the Alexa or Google Home app, add the
Lumen skill or action and sign in with your Lumen account. Rename lights in the Lumen app
first; voice assistants use those names.
"""

FAQ_CSV = """question,answer
How do I reset my password?,"Open the Lumen app or lumen.example/signin, tap Forgot password and enter your email. The reset link works for 30 minutes. Check your spam folder if it does not arrive."
How long does shipping take?,"Standard shipping takes 3 to 5 business days. Express shipping takes 1 to 2 business days. You get a tracking link by email as soon as your order ships."
Can I track my order?,"Yes. Open the shipping confirmation email and click Track package, or sign in at lumen.example/orders to see the latest status."
What is your return policy?,"You can return unused products within 30 days of delivery for a full refund. Start a return from lumen.example/orders; we email you a prepaid label."
How long is the warranty?,"Lumen bulbs have a 3 year warranty and the Lumen Bridge has a 2 year warranty, covering manufacturing defects."
What does Lumen Plus include?,"Lumen Plus costs 4.99 dollars a month and adds unlimited scenes, 90 days of energy history, away-mode lighting and priority support."
How do I change my plan?,"Open the app, go to Settings, Subscription, and pick a plan. Upgrades start immediately; downgrades take effect at the next renewal date."
Which payment methods do you accept?,"We accept Visa, Mastercard, American Express, PayPal and Apple Pay. Business customers can pay by invoice."
Where can I download my invoice?,"Sign in at lumen.example/account, open Billing and click Download next to any invoice. Invoices are PDF files with your company details."
Do Lumen bulbs work without internet?,"Yes, with a Lumen Bridge: lights, scenes and schedules keep working on your home network. Without a Bridge, you can still use the wall switch."
How many bulbs can I connect?,"Up to 10 bulbs connect directly over Wi-Fi. With a Lumen Bridge you can connect up to 50 bulbs per Bridge."
Is my data private?,"Lumen stores only what the app needs to run your lights. We never sell personal data. You can export or delete your data at lumen.example/privacy."
Can I share control with my family?,"Yes. In the app, go to Settings, Home, Members and invite people by email. Members can control lights but cannot change the subscription."
Why is my bulb flickering?,"Flickering usually means a dimmer switch. Lumen bulbs must be on a regular on and off switch, not a wall dimmer. Set the wall dimmer to full or replace it with a plain switch."
Does Lumen work with Apple Home?,"Not yet. Lumen works with Amazon Alexa and Google Home today."
How do I add a bulb to a room?,"Open the app, tap the bulb, choose Room and pick or create a room. Rooms let you control several bulbs together."
What colours can the bulbs show?,"Lumen Colour bulbs show 16 million colours and whites from 2200 K warm to 6500 K daylight. Lumen White bulbs show whites only."
How much energy does a bulb use?,"A Lumen bulb uses 9 watts at full brightness, equivalent to a 60 watt incandescent bulb, and under 0.5 watts on standby."
"""

SHIPPING_HTML = """<!doctype html>
<html><head><title>Shipping and returns</title></head>
<body>
<nav>Home | Shop | Support</nav>
<main>
<h1>Shipping and returns</h1>
<h2>Where we ship</h2>
<p>We ship to the United States, Canada, the United Kingdom, the European Union, India and Australia.
Orders over 50 dollars ship free with standard shipping.</p>
<h2>Delivery times</h2>
<p>Standard shipping takes 3 to 5 business days. Express shipping takes 1 to 2 business days.
Orders placed before 2 pm ship the same day.</p>
<h2>Damaged or missing items</h2>
<p>If a package arrives damaged or an item is missing, contact us within 14 days of delivery with a photo
of the package. We send a replacement at no cost.</p>
<h2>Returns</h2>
<p>Unused products can be returned within 30 days of delivery. Refunds go back to the original payment method
within 5 business days after we receive the return.</p>
</main>
<footer>Lumen Lighting</footer>
</body></html>
"""

WARRANTY_TEXT = [
    "Lumen Limited Warranty",
    "Lumen bulbs are covered for 3 years and the Lumen Bridge for 2 years from the date of purchase.",
    "The warranty covers defects in materials and workmanship under normal use.",
    "It does not cover damage from power surges, water, dimmer switches or unauthorised repairs.",
    "To make a claim, contact support with your order number and a short description of the fault.",
    "We replace a faulty product with the same or an equivalent model and pay for shipping both ways.",
]

BUSINESS_DOC = [
    ("Lumen for Business", "title"),
    ("Volume pricing", "heading"),
    (
        "Orders of 25 bulbs or more get 10 percent off; 100 bulbs or more get 18 percent off.",
        "text",
    ),
    ("Business customers can pay by invoice with 30 day terms after a credit check.", "text"),
    ("Installation", "heading"),
    (
        "Certified partners install Lumen in offices, hotels and shops. Ask support for a partner near you.",
        "text",
    ),
    ("Central management", "heading"),
    (
        "The Lumen Business console manages many sites, schedules and access for staff from one place.",
        "text",
    ),
]

ARTICLES = [
    (
        "Pairing a new bulb",
        "technical",
        "## Before you start\n\nMake sure your phone is on a **2.4 GHz** Wi-Fi network.\n\n"
        "## Steps\n\n1. Switch the lamp on. The bulb blinks blue.\n2. Open the Lumen app and tap **Add device**.\n"
        "3. Follow the steps. Pairing takes about a minute.\n\nIf the bulb does not blink blue, reset it: switch it off "
        "and on five times.",
    ),
    (
        "Updating your payment method",
        "billing",
        "Go to **Settings > Subscription > Payment method** in the app, or Billing at lumen.example/account. "
        "Add the new card first, then remove the old one. Your next charge uses the new card.",
    ),
    (
        "Setting up away mode",
        "technical",
        "Away mode turns lights on and off at natural times while you travel, so the home looks lived in. "
        "It is part of **Lumen Plus**. Open **Automations > Away mode**, choose the rooms and the dates.",
    ),
    (
        "Changing the email on your account",
        "account",
        "For your security, email changes are handled by our team. Write to support from your current email address "
        "and tell us the new one; we confirm both addresses before switching.",
    ),
    (
        "Energy reports explained",
        "general",
        "The Energy tab shows how much each light used this week and month. Lumen Plus keeps 90 days of history. "
        "Costs use the electricity price you set in **Settings > Home**.",
    ),
]
DRAFT_ARTICLE = (
    "Using Lumen with Apple Home",
    "technical",
    "Apple Home support is on our roadmap. In the meantime you can control Lumen with Alexa or Google Home.",
)

MACROS = [
    (
        "Ask for order number",
        "Thanks for reaching out! Could you share your order number? It starts with LUM and you "
        "can find it in your confirmation email.",
        {"status": "pending"},
    ),
    (
        "Pairing checklist",
        "Let's get your bulb paired. Please check that your phone is on a 2.4 GHz Wi-Fi network, then "
        "reset the bulb by switching it off and on five times. It should flash white three times, then blink blue.",
        {},
    ),
    (
        "Replacement on the way",
        "I'm sorry about the trouble. I've arranged a free replacement, which ships today with "
        "express delivery. You'll get the tracking link by email.",
        {"status": "resolved", "tags": ["replacement"]},
    ),
    (
        "Refund confirmed",
        "Your refund has been issued to the original payment method. It usually appears within 5 "
        "business days.",
        {"status": "resolved", "tags": ["refund"]},
    ),
    (
        "Closing follow-up",
        "I'm closing this conversation for now. If anything else comes up, just reply here and it "
        "reopens.",
        {"status": "resolved"},
    ),
]
