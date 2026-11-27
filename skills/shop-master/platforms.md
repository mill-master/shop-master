# The three platforms, as read by the adapters

Everything here was observed on 2026-11-27 from a connection in Tbilisi, for a delivery point at Freedom Square (41.6938, 44.8015), without an account, unless a line says otherwise; what was seen in other countries has a section of its own. An amount written with a decimal point is in lari; a whole number quoted from a platform's field is in tetri, the hundredth of a lari. Counts of stores or products sampled are of one-off reads made on that date, whose replies are not kept in the repository.

Two terms recur. A platform's web client is its own web site, whose calls the adapters repeat. The planning estimate is the fee total the tool computes from a store's rules before any basket is priced by the platform; on Wolt the checkout call then replaces it for the baskets of each listed plan. Each platform's adapter (`lib/wolt.py`, `lib/glovo.py`, `lib/bolt.py`) holds the request details; this page holds what was learned that the code alone does not show.

## Connectors and MCP servers

- **Glovo** runs an official search-only MCP server at `https://api.glovoapp.com/discovery-mcp/mcp` (tools `search_products` and `render_products_carousel`). It answers `403 Forbidden` to local clients: a plain JSON-RPC `initialize`, the MCP inspector, and Claude Code's own HTTP client were all refused, while a nonexistent path beside it returns `404`. Glovo's own page documents it as a connector chosen inside Claude's Connectors settings, and connector directories describe it for other assistants as well. It returns products and store details and no fee rules, so the adapter reads the web client's calls instead.
- **Wolt** has no official server. Two unofficial ones exist, both built on the web client's calls and both able to fill a signed-in basket: `github.com/erlaufer/wolt-mcp`, and `github.com/mekedron/wolt-mcp`, which is the one listed at `mcpmarket.com/server/wolt`. The first one's source documents Wolt's token refresh and basket endpoints, and was read for the request headers used here. Neither is a dependency.
- **Bolt Food** has no MCP server or published consumer client that a search of GitHub and the MCP directories turned up. `developer.bolt.eu` documents the merchant side only.

## What the platforms' terms say

- **Wolt** (Georgia, updated 30 June 2025), clause 13.6: the user will not "collect, use, copy, or transfer any information obtained from the Wolt Service without the consent of Wolt", "use bots or other automated methods to use the Wolt Service", or "access the Wolt Service except through the interfaces expressly provided by Wolt, such as the Wolt App and Wolt Website".
- **Bolt Food** (Georgia, effective 14 November 2026), clause 8.5: users "are expressly prohibited from engaging in any form (manual or automated) of data scraping, data mining, data extraction, or any automated collection of data from the Bolt Food Platform".
- **Glovo**: its terms page refused an automated read, so its clause was not seen.

## Wolt

Calls, all accepted from a plain HTTP client with the web client's headers and no cookies:

| Purpose | Call |
|---|---|
| Items across stores | `POST restaurant-api.wolt.com/v1/pages/search` with `{q, target: "items", lat, lon}`; up to 200 hits, each naming its store and a `product_line` such as `grocery`, `restaurant` or `pharmacy` |
| Items in one store | `POST consumer-api.wolt.com/consumer-api/consumer-assortment/v1/venues/slug/{slug}/assortment/items/search?language=en` with `{q}`; works for restaurants too |
| Store, fixed facts | `GET consumer-api.wolt.com/order-xp/web/v1/pages/venue/slug/{slug}/static` |
| Store, for a delivery point (the dynamic call) | `GET consumer-api.wolt.com/order-xp/web/v1/venue/slug/{slug}/dynamic/?lat=&lon=` |
| Price a basket | `POST consumer-api.wolt.com/order-xp/web/v2/pages/checkout` |

The search reply does not say whether a store is taking orders: some open stores come without a delivery time, as closed ones do. The dynamic call does.

### The checkout call

It is what makes Wolt exact. It prices a basket without login and without storing anything, and its fees matched those of wolt.com's own cart for the same basket and point (bag 0.40, small order 3.85, service 1.63 on goods of 20.39). Each line needs `id`, `count`, `base_price`, `end_amount`, `options`, `restrictions`, `exclude_from_discounts` and `category_id`. The last is the shelf category the product sits in, which the store's own item search returns as `categories[].item_ids`; checkout matches category campaigns on it and takes whatever the request says.

- It takes the goods' prices from the request, and accepts an item id that does not exist. A one-line basket of any amount therefore reads the store's fees at that amount.
- The **small order fee** is the exception: for a real item it is reckoned on the catalogue's price before any price cut. Four milks at 5.49 (was 6.25) paid none against a minimum of 25.00, though they cost 21.96.
- It applies the campaigns whose ids arrive in `use_promo_discount_ids` and whose conditions the basket meets, and shows the result as a lowered "Item subtotal" beside its original amount. The adapter sends every campaign that is not limited to new customers or Wolt+ members, and for a signed-in account all of them.
- It accepts a count above a product's `max_quantity_per_purchase` and above its stock without complaint (eight of a product limited to three, nine of a stock of five), so those limits are not enforced where a basket is priced. The tool reports them.

### Fees

Measured through that call, at a grocery store (Wolt Market Baratashvili, small-order minimum 2500) and a restaurant (small-order minimum 1200):

- **Service fee**: 8% of the goods after product discounts, floor 100, cap 499, at both. Checkout states the rule in its fee explanation. A discount on the whole basket does not lower it.
- **Small order fee**: the gap up to the store minimum, capped at 399 for the grocery store and 299 for the restaurant. The cap appears nowhere in the store's published data.
- **Delivery**: one amount per store and delivery point, the same at every basket size, and equal to `delivery_specs.original_delivery_price` in the dynamic call. It moved during the day: 2.59 at night and 1.59 in the afternoon for the same store and point.
- **Bag**: the store's `bag_fee` for every started ten items (40 per ten at the grocery store); none at the restaurant. The planning estimate counts one bag.

`delivery_specs.delivery_pricing.price_ranges` in the dynamic call gives the service fee as bands `a + b × subtotal`. Its first band falls as the basket grows (`b = -1`), which checkout does not charge: it charges the floor there. The adapter flattens that band; `tests/test_fees.py` holds both measured tables.

### Campaigns and offers

A store's `discounts` in the dynamic call are of three kinds.

- **On products** (`item_discount`), naming in `include` the item ids or the shelf categories it covers. The shelf shows these products at full price; checkout takes the discount off each unit, rounded on the unit. Measured:
  - a share of the price (`fraction`): a 30% campaign priced a shampoo listed at 87.95 at 61.56, and three units of 9.95 at 20.88 (6.96 each), where 30% off the line would give 20.89;
  - on a category: a wafer listed at 1.99 after a cut from 3.95 was charged 1.39 under a 30% campaign on its category, with the category's id on the line, and 1.99 with any other id. Of 21 product campaigns in the stores sampled, 6 named categories. Whether a campaign can name a parent of the category a product is listed under was not seen;
  - a fixed amount (`amount_per_item`): "3 GEL off" took 8.21 to 5.21, three units to 15.63, and a 2.00 unit to nothing;
  - sparing a dish's choices (`exclude_options`): a combo at 19.90 with a 5.00 choice under a 32% campaign came to 18.45, the discount taken on the 19.90 alone;
  - from several units (`min_quantity` in the conditions): "Buy any 2x … get 30% off" brought two at 24.50 to 34.30. The count runs across the different products the campaign covers: two different ones at 24.50 also came to 34.30. The planning estimate counts each product's units alone, and the checkout call corrects it for a listed plan.

  One grocery store ran thirteen product campaigns on ninety products. Overlapping product campaigns were not met.
- **On the basket** (`basket_discount`), with a minimum in `conditions.basket_contains`. Measured: "10% off (up to GEL20) on orders over GEL50" took 6.00 off 60.00 and 20.00 off 300.00, nothing off 40.00; "GEL50 off on orders over GEL200" took 50.00 off 250.00. Given a new-customer basket offer together with one for every customer, checkout applied one of the two, so these do not add up.
- **On delivery** (`delivery_discount`), sometimes with a basket minimum and a `max_distance` in metres. "GEL0 delivery fee on orders over GEL20" within 5,000 m, at a store 2.4 km away: delivery 3.09 on goods of 16.90 and nothing on 33.80. The adapter counts such an offer when the store is within the distance.

A plain price cut is different: the product's `price` is already the lower one and `original_price` the old one, with no campaign behind it.

An anonymous visitor is shown new-customer offers ("GEL0 delivery fee", "GEL12 off on orders over GEL30"), marked as such only in their description text. The store page's displayed delivery price of zero comes from them.

Of some thirty stores and restaurants sampled, three ran a basket offer for every customer, one restaurant ran free delivery for every customer with no minimum, and one store free delivery above a basket amount.

### Products

- A dish's `options` bind it to choice groups defined beside the items; `multi_choice_config.total_range.min` says how many choices are obligatory. A "Khachapuri set" listed at 2.00 needs three choices at 15.00 each. The adapter adds the cheapest obligatory choices and states them at checkout.
- A weighed item carries `sell_by_weight_config` with `price_per_kg` and `grams_per_step`; its `price` is the price per kilogram and its stock figure is in grams. It is bought in whole steps.
- `unit_info` gives the pack size, and at some stores belongs to another product (a pack of fifteen eggs labelled 400 g). The adapter reads the size from the name first. Names are mislabelled too: thirteen wines were named "0.75ml" and a cheese "0.25g". A size under one gram or millilitre is read as no size.
- `max_quantity_per_purchase` limits how many one order may take (three of a cheese). `available_times` restricts some items to hours of the day, which the adapter does not check.

## Glovo

The API refuses requests without most of the web client's `glovo-*` headers (the adapter sends the set that worked), and store calls need the city and country codes, which `GET /v3/addresslookup/pub/coordinates` returns for a coordinate pair. The delivery point travels in headers. Bursts are answered with `429`.

| Purpose | Call |
|---|---|
| Stores and matching products | `POST /v1/web/store_wall/search?searchQuery=`, optionally `&categoryId=` (1 is restaurants and 4 groceries; 3 and 22 also occur on store cards). Without a category it shows products only for the stores it ranks first, so when that is fewer than three stores the groceries are searched on their own as well |
| One store | `GET /v3/stores/{slug}?includeClosed=true&includeDisabled=false` |
| Items in one store | `GET /v3/stores/{id}/addresses/{addressId}/search?query=` |
| Small-basket surcharge | `GET /v1/stores/{id}/addresses/{addressId}/node/store_fees` |

The search answers with a screen description: a card per store, followed by a row of that store's matching products with display prices. A store's open state and category sit in the card's display-tracking event.

Fee parameters as published, for a supermarket (SPAR): delivery 1.49 lari; `serviceFeeInfo` of `setupValue` 9 with `minValue` 229 and `maxValue` 699; one surcharge range from 0 to 30 lari of 2.99 lari with strategy `CAPPED`. A restaurant showed 9 / 129 / 499 and a 1.99 surcharge below 15 lari.

- The **surcharge** is the gap up to the range's end, at most the stated amount. A guest basket's own footer (`GET /v2/guest/customers/{id}/stores/{storeId}/addresses/{addressId}/mbs/footer`) gave 2.99 on a basket of 11.20 and 2.00 on one of 28.00, against a threshold of 30.00.
- The **service fee** is read as that percentage between the two bounds. This has not been checked against a priced order: the call that prices one, `POST /v3/checkouts/order/1/template`, needs a signed-in customer.
- The **delivery price** moves during the day: the same store and point showed 1.49 at night and 4.99 in the afternoon.

A product's `promotion.price` is its discounted price; `promotion.isPrime` marks a subscriber-only price, which the adapter leaves out of the total. Products carry no size apart from their name and no mark for goods sold by weight.

A dish's `attributeGroups` are its choices, each with `min`, `max` and options carrying a `priceImpact`. A combo listed at 13.90 had one obligatory group whose options added 1.95 or 3.90, so it cannot be had under 15.85. The adapter adds the cheapest obligatory options. Whether a percentage promotion also lowers the options was not seen.

Store pages live at `glovoapp.com/en/{country}/{city}/stores/{slug}`, the city being the locality's name in plain letters (`tbilisi`, `barcelona`). Under another name, such as the region's, the address still answers, with a reduced page.

A store's `promotions` were of four kinds across some thirty stores and restaurants: `FREE_DELIVERY` "on the first order" at every one of them; `FLAT_PRODUCT` and `PERCENTAGE_DISCOUNT` on "select items", some of the latter "with Prime"; and, at one restaurant, `BASKET_PERCENTAGE` on the "whole menu" with a `minimumBasketSizeCents` of 4000. The adapter counts the last kind, when it is not for Prime members, as that percentage off a basket of at least that size. This reading is unchecked.

## Bolt Food

Calls go to `deliveryuser.live.boltsvc.net/deliveryClient/public/{method}` with a query string naming the web client and a random device id; no other header is needed. A reply carries `code: 0` on success.

| Purpose | Call |
|---|---|
| Providers matching a query | `POST deliverySearch` with `search_tab_id` of `stores` or `restaurants` |
| Matching items in those providers | `POST getProviderPreviewMenuItems` with the provider ids, twenty at a time |
| Items in one provider | `GET searchInMenu?provider_id=&search_string=` |
| One provider | `POST getProviderOverview` |

Prices are decimal amounts in the country's currency, for the pack as named. `selling_unit` of `kg` does not mean the price is per kilogram: a "Gouda briquette 100 g" at 4.50 carries `unit_price` "45,00 ₾/kg" beside it. The two together give the pack's weight. Of the products sold by `kg` that were sampled, 22 carried no `unit_price` ("Danablue 2*3.2 kg" at 6.50, an apple at 4.45), and what their price covers could not be told without a priced basket; the adapter gives such a product no size. `order_limit_quantity` limits how many one order may take.

`option_group_presence` other than `none` marks a dish with choices, and the menu search reply carries them: each group (`option_multi_select_group`) with its `min` and `max`, and each option with its price. A "Pizza 33Cm" listed at 0.10 needs two halves, the cheapest at 10.95 and 13.95. The adapter adds the cheapest obligatory options, each taken once; whether one option may be taken twice was not seen. Of some 750 items previewed, 115 had obligatory choices.

An anonymous visitor gets the delivery price and nothing more. `getProviderFeeDisclosure` lists a small order fee, a service fee and a packaging fee by name and ends "Sign in to see fee estimates", and `min_price_details` was empty in every menu read. Bolt totals from the adapter are therefore lower bounds.

Provider pages live at `food.bolt.eu/en-US/{city_id}/p/{slug}`.

## Other countries

The tool was run signed out on 2026-11-27 for delivery points in the cities named below. The clauses quoted under the terms above are the Georgian ones, and the subscription figures further down are Georgia's.

### Wolt

The planning estimate of a store's fees was compared with Wolt's pricing of the same basket at five sizes, from under the small-order minimum to over the service-fee cap, at one store each in Budapest, Reykjavik, Tel Aviv, Almaty, Stockholm, Copenhagen, Oslo and Athens. The two were equal everywhere but for the bag charge in Oslo. Whole runs were priced in Helsinki, Reykjavik and Budapest.

- Wolt states an amount in the currency's smallest unit, and for the Icelandic krona that is the krona: "ISK1,500 off" carries 1500, where "HUF 1,500 off" carries 150000. Each amount in a checkout reply comes with its wording (`amount` 869 beside `formatted_amount` "ISK869"; 159 beside "GEL1.59"), and the adapter reads the unit from one such pair and keeps every amount in hundredths. Before it did, a total of 2,607 kronur was printed as 26.07. Points in Tokyo and Sapporo returned nothing, so the yen is unmeasured.
- A deal that needs a code, or pays in loyalty points, is published as a basket discount of one smallest unit: "₪25 off with code BF25W" at a store in Tel Aviv and a points scheme at one in Budapest both carried `amount` 1, and checkout took that one unit off when given the campaign's id. The adapter lists such a campaign and keeps it out of the arithmetic and out of the ids it sends.
- The bag charge at the Oslo store was 4.00 for one item, 8.00 for ten and for eleven, and 16.00 for twenty-five. The rule behind those figures was not worked out. The planning estimate counts one bag, and Wolt's pricing of the basket has the real charge.

### Glovo

- Restaurants are category 1 in Milan, Lisbon, Belgrade, Casablanca, Almaty, Kyiv, Nairobi, Bucharest and Warsaw.
- Some forty stores in Milan, Lisbon, Belgrade, Casablanca, Almaty, Kyiv, Warsaw and Nairobi all published one surcharge range starting at nought, with strategy `CAPPED`; no other strategy was met. The fee parameters came in the units the adapter expects in złoty, shillings, tenge, Serbian dinars, dirhams, hryvnias and lei. Store links opened in each of those cities and in Bucharest.
- A search without a category shows products only for the stores it ranks first. For "huevos" in Barcelona it returned a hundred store cards, 83 of them restaurants, and product rows for restaurants alone; with `categoryId=4` it returned product rows for 22 grocery stores. "jajka" in Warsaw behaved the same. Hence the second search named in the table of Glovo's calls. A search among the groceries for a word they do not stock returns a screen with an element of no type.
- Glovo's address lookup names a city for any point on earth (`SUW` for Helsinki). For a country Glovo is not in, `GET /seo-content/locales/en/countries/{code}` answers `404` and a search answers `503` with "no available server", which a client that retries would wait on for about a minute. The adapter asks for the country page once in a run and, on a `404`, makes one search without retrying; the two answers together are reported as "Glovo does not operate in" that country. A point without stores in a country Glovo is in (a field west of Madrid) answered the search with `422`.
- In Warsaw one search came back in three shapes on separate tries: with 12 product rows, with 32, and with cards of the type `STORE_TILE_COMPRESSED` and no product rows at all. What decides the shape was not found.
- A search card's display price in a currency of three decimals ("22,650 DT" in Tunis) is read a thousand times too high. That price is used only to rank the stores of one search against each other.

### Bolt Food

The search tabs `stores` and `restaurants` answer in Riga, Sofia, Prague, Warsaw and Nairobi, and whole runs finished in Tallinn, Riga, Sofia and Prague. A point Bolt does not serve answers `CITY_NOT_FOUND` (Reykjavik) or an empty list (Helsinki, Zagreb, Lagos).

### Catalogues

Product names are in the country's language on Glovo, and in English on Wolt in Reykjavik, Helsinki and Tel Aviv; Bolt in Sofia gave transliterated names without sizes. The pack sizes read are metric units and piece words in Latin, Georgian and Cyrillic letters, with the Polish, Czech, Spanish and Icelandic spellings met ("20 szt.", "6 ks", "6 Uds.", "1 ltr"). A dozen written as a word ("Docena") is not read, and milk sold by weight (0.87 kg in Kyiv) does not compare with a request in litres. Such a candidate stands for nothing until whoever runs the tool gives the count to buy.

## Subscriptions

As the platforms describe them on their own pages; none of it is computed.

- **Wolt+** (`explore.wolt.com/en/geo/wolt-plus`): 8.99 lari a month. No delivery fee at venues marked W+, within 4 km, on baskets from 15 lari at restaurants, 20 at retailers and 35 at grocery stores. Up to 80% off the service fee, more the nearer the venue. Stores sampled in Tbilisi carried `show_wolt_plus: false` for an anonymous visitor.
- **Glovo Prime** (`glovoapp.com/en/ge/tbilisi/glovo-prime`): 8.99 lari a month. "Unlimited free deliveries" at Prime restaurants, supermarkets and shops, and "lower fees on every order"; no figures. Stores report `primeAvailable`.
- **Bolt Plus** (`bolt.eu/en-ge/plus/`): free delivery with Bolt Food at venues carrying its logo, up to a maximum saving per order and above a minimum order, both unstated for Georgia.

## Signed-in access

The calls in this section are read from the code of each platform's own web site, and where one was also tried signed out, its answer is given. On 2026-11-27 one real account tried the routes, and what that showed is marked "seen with a real account"; the rest is unconfirmed. A reply that has not been seen is not trusted to have the form the code expects: a sign-in step answered in another form stops with a message naming what was missing, a token renewal keeps a new refresh token whatever else its reply holds, and a basket priced for an account in a form the tool cannot follow is priced as a visitor's, with a note. Three open-source Wolt clients were read as well: the unofficial servers `erlaufer/wolt-mcp` and `mekedron/wolt-mcp`, and `mekedron/wolt-cli`, on which the second is built.

With an account, and in a run the shopper chose to make signed in, the tool prices a basket on Wolt; on Wolt and Glovo it reads who is signed in and whether a subscription shows. It fills no cart. The basket and checkout calls noted below are what was learned towards that. No basket has yet been priced for a real account.

### Wolt

- **By e-mailed link.** Asking for the link (`POST authentication.wolt.com/v3/users/email_login`) carries an invisible hCaptcha, so the shopper asks for it at wolt.com. The link's `token` is redeemed by a form post, `POST /v1/wauth2/access_token` with `grant_type=email_login`, `audience=wolt-com` and `capabilities=access_confirmation`. A made-up token answered `401` with `error_code` 126. An `error_code` of 130 asks for a code sent by e-mail: `/v1/access_confirmation/email`, then `/email/submit`, then the token call again with `grant_type=access_confirmation_token`.
- **By phone**, which Wolt's web dialog does not offer and its service answers. `POST /v1/captcha/site_key` with `{phone_number, operation: "start_phone_number_authentication_consumer"}` returns an `operation_token`, and a `site_key` that is null when no captcha is wanted. `POST /v2/wauth2/consumer-sms/start-phone-number-authentication` with `{phone_number, message_delivery_method: "sms", operation_token}` sends the code, and the token call redeems it with `grant_type=phone_number_otp`, `phone_number`, `otp` and `tenant=wolt`. When a `site_key` comes back the tool stops, since it solves no captcha.
- **Seen with a real account:** the phone route was answered with a `site_key`, a captcha demand, so the tool stopped. Through a browser window the session was taken from the two cookies named below, and `GET restaurant-api.wolt.com/v1/user/me` and the subscriptions call both answered it.
- **Renewal** is the token call with `grant_type=refresh_token`. It may hand back a new refresh token, which replaces the old.
- **Signed-in calls** carry `authorization: Bearer`. `GET consumer-api.wolt.com/subscriptions-api/v1/subscriptions` lists the account's subscriptions, lapsed ones included, each with `plan.name` and with `start_date`, `next_payment_date` and `paid_until_date` as moments in seconds (`end_date` was null on a running one). One is held while `paid_until_date` lies ahead.
- **Basket**, per the three clients: written with `POST /order-xp/v1/baskets`, a whole replace for that store in which a line's `price` is the line total; read with `GET /order-xp/web/v1/pages/baskets`; removed with `POST /order-xp/v1/baskets/bulk/delete`.

### Glovo

- **By e-mail and password**, with no captcha. A device is registered at `POST /identity/v4/devices`; `GET /v3/customers/auth/{email}/methods` lists the account's sign-in methods (an address with no account answered an empty list); `POST /oauth/token` with `{grantType: "password", username, password}` returns the tokens or asks for a second step.
- **By phone**, and for that second step, the request carries a reCAPTCHA token, and in Georgia the phone code comes by WhatsApp. The tool has no call for either.
- **Renewal** is `POST /oauth/refresh` with the refresh token, under the registered device's `glovo-device-urn`; the reply carries a new refresh token. The access token travels as a bare `Authorization` value.
- `GET /customers/{id}/subscription/status` reports Prime.
- **Seen with a real account:** an account opened with a phone number signed in through a browser window. The session was taken from the local storage named below, and `/v3/me` and the subscription status both answered it.
- **Basket.** A guest basket was read, written (`PUT /v2/guest/customers/{id}/baskets/{basketId}` with the whole basket) and deleted on the wire; the signed-in calls drop `guest/customers/{id}` from the path. `POST /v3/checkouts/order/1/template` builds the priced checkout screen without ordering; the calls beside it without `/template` place an order.

### Bolt Food

The tool does not sign in to Bolt Food. Its web site signs in by phone number and texted code, `POST /profile/verification/start` and then `/profile/verification/confirm`, on the same host as the catalogue. Seen with a real account: the first of those calls, made by this tool, was answered `BLOCKED_BY_FRAUD`. That is Bolt's fraud protection refusing the sign-in, and the tool takes it as final: the sign-in was removed, and nothing is done to get past the refusal. Bolt is read signed out, with its totals as lower bounds, and whether a shopper holds Bolt Plus is asked of the shopper.

### Signing in through a browser window

`login wolt --browser` and `login glovo --browser` are the routes that have signed a real account in, and the only ones for an account the calls above cannot sign in: a Glovo account opened with a phone number, a sign-in through Google, Apple or Facebook, a Wolt sign-in for which a captcha is wanted. The shopper signs in by hand on the platform's own page, in a browser window the tool opens on a browser profile it creates for the occasion. When the shopper has closed the browser, the tool starts it again on that profile without a window, reads the session the site left there, and deletes the profile. From then on the session is used and renewed like one made in the terminal.

Two decisions shape this.

- The window carries no debugging channel, and the tool learns that the sign-in is over from the browser closing. With Chrome 158 on Linux, a page in a window opened with a debugging port saw `navigator.webdriver` as true, and a page in a plain window saw it as false. A sign-in page can read that flag, and these pages run captchas.
- The session is read from a profile of the tool's own and not from the shopper's everyday browser, so that the tool is its one holder. Renewal replaces the refresh token on both platforms (Wolt's may be replaced, Glovo's reply carries a new one), and two holders of one token would sign each other out.

What each site keeps, read from the code of its web site:

- **Wolt**: two cookies on `wolt.com`, kept for a year. `__wtoken` holds `{accessToken, expirationTime}` as JSON and `__wrtoken` the refresh token as a JSON string, each encoded as a cookie value. `mekedron/wolt-cli` takes a session from a browser it opens in the same way.
- **Glovo**: in the local storage of `glovoapp.com`, `glovo_refresh_token` as a JSON string and `glv_device` as `{fingerprintsExpirationTime, urn}`, the registered device that a renewal names. The access token sits in the cookie `glovo_auth_info` as `{accessToken}`.

What was measured, with Chrome 158 on Linux and a local test page standing in for a platform's:

- A cookie and a local-storage value that the page wrote in a window were on disk after the browser was quit in the ordinary way six to eight seconds later, and the same browser run without a window read both back. When the browser was ended with `SIGTERM` in place of an ordinary quit, the cookie was not on disk.
- Both the window and the windowless run are started with `--password-store=basic`, which keeps the profile's cookies under the browser's built-in key. Without it the windowless run would need the desktop's keyring to read them.
- The windowless run fetches nothing from the site. Cookies come from the browser's own store, and the page whose local storage is read is answered inside the browser.

## How the tool asks

The tool limits itself in the ways below. The figures are its own choice, made for restraint: no platform publishes a limit, and the observations after the list are all there is to go on.

- One request a second to a host, and three seconds between requests made for a signed-in account. The moment a host may next be asked is kept on disk (`pace.json`, beside the saved run), so every run on the computer shares one pace.
- At most 300 requests to a host in an hour, of which at most 40 for an account. A further request is refused before it is sent, with the time from which it may be made. For scale, a comparison of four items sent about 60 requests to each platform's main host.
- An answer of `429`, `502`, `503` or `504`, or a dropped connection, is tried again up to three times after growing waits, and the wait after a `429` holds every run off that host.
- A host that answers `429` to every attempt of one request is left alone for ten minutes. Requests to it are refused before they are sent, in every run, with the time from which it may be asked again.
- A request made for an account, or one that signs in, is made once and not retried. After a `429` the account is left alone for an hour, and after a `401` or `403` until the shopper signs in again; baskets are priced as a visitor's meanwhile.
- Searches, shelves and stores are read without the account on every platform, signed in or not.
- A run uses an account only when the shopper chose a signed-in run. The tool gathers nothing for a new run until that choice is given, and a run made signed out asks nothing in the shopper's name though sign-ins are kept.

What was observed of the platforms' own throttling: Glovo answered `429` in most runs at three requests a second and in none at one a second. Wolt's store call for a delivery point answered `429` after about a dozen requests in quick succession. Some 110 requests to Wolt spread over twenty minutes met no throttle. Volume counts as well as pace: after a day of testing that asked Glovo several hundred times an hour from one connection, it answered `429` to requests a second apart, and each retry added to the count. The hourly figure and the ten minutes of rest were set after that.

This restraint lowers the chance of being throttled. It does not make the use one the platforms' terms allow.
