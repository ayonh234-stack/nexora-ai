# Nexora-কে আপনার Instagram-এর সাথে যুক্ত করার গাইড (অফিশিয়াল ও নিরাপদ উপায়)

এই পদ্ধতিতে Nexora **Instagram-এর অফিশিয়াল API** দিয়ে কাজ করে। আপনার Instagram পাসওয়ার্ড কোথাও দিতে হয় না, তাই অ্যাকাউন্ট ব্লক হওয়ার ঝুঁকি নেই। পুরোটাই **ফ্রি**, কোনো কার্ড লাগে না।

যুক্ত হলে Nexora যা করতে পারবে:
- 📸 ছবি, ক্যারোসেল (একাধিক ছবি) আর রিল পোস্ট, ক্যাপশন ও হ্যাশট্যাগসহ
- 🗓️ নিয়মিত পোস্ট, যেমন প্রতিদিন রাত ৮টায়। প্রতিটা পোস্টের আগে Telegram-এ আপনার ✅ অনুমোদন নেবে (চাইলে অটো মোড)
- 💬 আপনার পোস্টের কমেন্ট পড়বে, AI দিয়ে রিপ্লাই লিখে আপনার অনুমোদনে পাঠাবে, স্প্যাম কমেন্ট লুকাবে
- 🧲 যারা কমেন্ট বা DM-এ সার্ভিসে আগ্রহ দেখায়, তাদের লিড লিস্টে রাখবে আর Telegram-এ জানাবে
- 📊 ফলোয়ার, রিচ আর পোস্টের পারফরম্যান্স জানাবে

> Nexora কখনো অন্যের পোস্টে নিজে থেকে কমেন্ট করবে না। Instagram-এর নিয়মে এটা করা যায় না, আর করলে অ্যাকাউন্টের ক্ষতি হয়।

---

## ধাপ ১: Instagram অ্যাকাউন্টকে Professional করুন (২ মিনিট)
1. Instagram app খুলে নিজের প্রোফাইলে যান → ডান দিকের ওপরে ☰ মেনু।
2. **Settings and privacy → Account type and tools → Switch to professional account**।
3. একটা ক্যাটাগরি বাছুন (যেমন *Digital creator* বা *Marketing agency*), তারপর **Business** বা **Creator** বেছে নিন।

## ধাপ ২: (শুধু উপায় খ-এর জন্য) একটা Facebook Page যুক্ত করুন
উপায় ক ব্যবহার করলে এই ধাপ লাগবে না।
1. Instagram প্রোফাইলে **Edit profile → Page** (বা Accounts Center) থেকে আপনার SocialGrowthLab Facebook Page বাছুন।
2. Page না থাকলে facebook.com থেকে ফ্রি একটা Page বানিয়ে নিন, তারপর যুক্ত করুন।

## ধাপ ৩: ফ্রি Meta Developer app বানান (৫ মিনিট)
1. কম্পিউটার বা ফোনের ব্রাউজারে **developers.facebook.com** খুলুন, আপনার Facebook দিয়ে লগইন করুন। প্রথমবার হলে **Get Started** চেপে developer হিসেবে রেজিস্টার করুন (ফ্রি, কার্ড লাগে না)।
2. **My Apps → Create App**।
3. নাম দিন, যেমন `Nexora SGL`, আর ইমেইল দিন।
4. Use case হিসেবে **"Manage messaging & content on Instagram"** বাছুন। না দেখালে **Other → Business** বাছুন।
5. **Create app** চাপুন। app-টা *Development* মোডে থাকবে, নিজের অ্যাকাউন্টের জন্য এটাই যথেষ্ট, App Review লাগবে না।

## ধাপ ৪: টোকেন বানান। দুটো উপায়ের যেকোনো একটা করুন

### উপায় ক (সবচেয়ে সহজ): Instagram Login দিয়ে, Facebook Page লাগে না
1. app-এর Dashboard-এ **Instagram → API setup with Instagram login** খুলুন।
2. **"Generate access tokens"** অংশে **Add account** চাপুন, তারপর @socialgrowthlabhq দিয়ে লগইন করে **Allow** দিন।
3. পাশে **Generate token** চাপুন। `IG...` দিয়ে শুরু হওয়া একটা লম্বা টোকেন আসবে। এটা কপি করুন।
   - এই টোকেন ৬০ দিন চলে। Nexora নিজে থেকে মেয়াদ বাড়িয়ে নেয়।
   - এখানে অনুমতিগুলো আপনাআপনি থাকে: instagram_business_basic, content_publish, manage_comments, manage_messages।

### উপায় খ: Facebook Login দিয়ে (Page যুক্ত থাকলে)
1. **developers.facebook.com/tools/explorer** (Graph API Explorer) খুলুন। ওপরে **Meta App**-এ আপনার app বাছুন।
2. **User or Page → Get User Access Token**।
3. **Add a Permission**-এ এগুলো টিক দিন:
   `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_messages`, `pages_show_list`, `pages_read_engagement`, `business_management`
4. **Generate Access Token** চাপুন। Facebook জিজ্ঞেস করলে আপনার Page আর Instagram অ্যাকাউন্ট বাছুন, তারপর Continue/Allow।
5. `EAA...` দিয়ে শুরু হওয়া টোকেনটা কপি করুন।
6. এই টোকেন ১-২ ঘণ্টায় শেষ হয়ে যায়। তাই app-এর **Settings → Basic** থেকে **App ID** আর **App Secret** (Show চাপুন) কপি করুন। Nexora এগুলো দিয়ে টোকেনকে ৬০ দিনের করে নেবে আর পরে নিজে নবায়ন করবে।

## ধাপ ৫: Nexora-তে টোকেন বসান। যেকোনো একটা করুন
- **Telegram (সবচেয়ে সহজ):** @SocialGrowthLabAI_bot-কে লিখুন
  `/ig token আপনার_টোকেন`
  উপায় খ হলে লিখুন `/ig token টোকেন APP_ID APP_SECRET`।
  বট সাথে সাথে আপনার মেসেজটা মুছে দেবে আর জানাবে "✅ @socialgrowthlabhq যুক্ত হয়েছে"।
- **ওয়েব app:** চ্যাটে `/vault` লিখে PIN দিয়ে ভল্ট খুলুন। তারপর মেনু → **📸 Instagram** → টোকেন বসিয়ে **Connect** চাপুন।

টোকেন এনক্রিপ্ট করে আপনার ভল্টে রাখা হয়, কখনো চ্যাটে দেখানো হয় না। শুধু আপনি (মালিক) এই ফিচার দেখতে পাবেন।

## ধাপ ৬: ব্যবহার শুরু করুন
Telegram বা ওয়েবে সাধারণভাবে লিখুন:
- "Instagram-এ অর্গানিক গ্রোথের টিপস নিয়ে একটা পোস্ট বানাও" → প্রিভিউ আসবে, ✅ চাপলে পোস্ট হবে
- "প্রতিদিন রাত ৮টায় একটা পোস্ট দিও, বিষয় Instagram গ্রোথ টিপস" → শিডিউল হবে। প্রতিদিন প্রিভিউ পাঠিয়ে আপনার অনুমোদন চাইবে
- "আমার পোস্টের নতুন কমেন্টগুলো দেখাও" / "এই কমেন্টের উত্তর দাও"
- "Instagram লিডগুলো দেখাও" / "এই সপ্তাহের ইনসাইট দাও"
- Telegram-এ ছবি পাঠিয়ে ক্যাপশনে লিখুন "ইনস্টাগ্রামে পোস্ট করো" → আপনার ছবি দিয়েই পোস্টের প্রিভিউ

নতুন কমেন্ট এলে প্রতি ১৫ মিনিটে Telegram-এ আসবে, সাথে AI-র লেখা রিপ্লাই আর বাটন থাকবে: ✅ পাঠাও / 🙈 লুকাও / ❌ বাদ।

Telegram কমান্ড:
- `/ig`: অবস্থা
- `/ig schedules`: শিডিউলের লিস্ট
- `/ig auto post on|off`, `/ig auto reply on|off`, `/ig auto spam on|off`: অটো মোড চালু বা বন্ধ
- `/ig disconnect`: সংযোগ বিচ্ছিন্ন

## সমস্যা হলে
- **"No Instagram professional account linked"**: ধাপ ১ আর ২ দেখুন (উপায় খ-তে Page লিংক লাগবে)।
- **"(#10) / permission" এরর**: টোকেন বানানোর সময় সব অনুমতি টিক দেওয়া হয়নি। আবার টোকেন বানিয়ে `/ig token` দিন।
- **টোকেনের মেয়াদ শেষ**: উপায় ক-তে Nexora নিজে নবায়ন করে। উপায় খ-তে App ID/Secret না দিলে নতুন টোকেন দিতে হবে।
- **DM পড়া** কাজ না করলে: উপায় ক-তে app-এর Instagram সেটিংসে messages অনুমতি চালু আছে কিনা দেখুন। উপায় খ-তে `instagram_manage_messages` লাগবে। এটা ছাড়াও কমেন্ট থেকে লিড ধরা চলবে।
- Instagram-এর নিয়মে দিনে সর্বোচ্চ ১০০টা API পোস্ট করা যায়, আর ছবি অবশ্যই JPEG হতে হয়। Nexora নিজে রূপান্তর করে নেয়।
