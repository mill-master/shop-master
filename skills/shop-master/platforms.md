# The three platforms, as read by the adapters

Everything here was observed on 2026-11-27 from a connection in Tbilisi, for a delivery point at Freedom Square (41.6938, 44.8015), without an account, unless a line says otherwise. Amounts are in tetri unless a field is marked as lari. Each platform's adapter (`lib/wolt.py`, `lib/glovo.py`, `lib/bolt.py`) holds the request details; this page holds what was learned that the code alone does not show.

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
| Store, for a delivery point | `GET consumer-api.wolt.com/order-xp/web/v1/venue/slug/{slug}/dynamic/?lat=&lon=` |
| Price a basket | `POST consumer-api.wolt.com/order-xp/web/v2/pages/checkout` |

The search reply does not say whether a store is taking orders: some open stores come without a delivery time, as closed ones do. The dynamic store call does.

### The checkout call

It is what makes Wolt exact. It prices a basket without login and without storing anything, and its fees matched those of wolt.com's own cart for the same basket and point (bag 0.40, small order 3.85, service 1.63 on goods of 20.39). Each line needs `id`, `count`, `base_price`, `end_amount`, `options`, `restrictions`, `exclude_from_discounts` and `category_id`.

- It takes the goods' prices from the request, and accepts an item id that does not exist. A one-line basket of any amount therefore reads the store's fees at that amount.
- The **small order fee** is the exception: for a real item it is reckoned on the catalogue's price before any price cut. Four milks at 5.49 (was 6.25) paid none against a minimum of 25.00, though they cost 21.96.
- It applies the campaigns whose ids arrive in `use_promo_discount_ids` and whose conditions the basket meets, and shows the result as a lowered "Item subtotal" beside its original amount. The adapter sends every campaign that is not limited to new customers or Wolt+ members.

### Fees

Measured through that call, at a grocery store (Wolt Market Baratashvili, minimum 2500) and a restaurant (minimum 1200):

- **Service fee**: 8% of the goods after product discounts, floor 100, cap 499, at both. Checkout states the rule in its fee explanation. A discount on the whole basket does not lower it.
- **Small order fee**: the gap up to the store minimum, capped at 399 for the grocery store and 299 for the restaurant. The cap appears nowhere in the store's published data.
- **Delivery**: one amount per store and delivery point, the same at every basket size, and equal to `delivery_specs.original_delivery_price` in the dynamic call. It moved during the day: 2.59 at night and 1.59 in the afternoon for the same store and point.
- **Bag**: the store's `bag_fee` for every started ten items (40 per ten at the grocery store); none at the restaurant. The planning estimate counts one bag.

`delivery_specs.delivery_pricing.price_ranges` in the dynamic call gives the service fee as bands `a + b × subtotal`. Its first band falls as the basket grows (`b = -1`), which checkout does not charge: it charges the floor there. The adapter flattens that band; `tests/test_fees.py` holds both measured tables.

### Campaigns and offers

A store's `discounts` in the dynamic call are of three kinds.

- **On products** (`item_discount`), each naming the item ids it covers. The shelf shows these products at full price; checkout takes the discount off. A 30% campaign priced a shampoo listed at 87.95 at 61.56. Some need several units ("Buy any 2x … get 30% off": two at 24.50 came to 34.30). One grocery store ran thirteen of these on ninety products.
- **On the basket** (`basket_discount`), with a minimum in `conditions.basket_contains`. Measured: "10% off (up to GEL20) on orders over GEL50" took 6.00 off 60.00 and 20.00 off 300.00, nothing off 40.00; "GEL50 off on orders over GEL200" took 50.00 off 250.00. Given a new-customer basket offer together with one for every customer, checkout applied one of the two, so these do not add up.
- **On delivery** (`delivery_discount`).

A plain price cut is different: the product's `price` is already the lower one and `original_price` the old one, with no campaign behind it.

An anonymous visitor is shown new-customer offers ("GEL0 delivery fee", "GEL12 off on orders over GEL30"), marked as such only in their description text. The store page's displayed delivery price of zero comes from them.

Of some thirty stores and restaurants sampled, three ran a basket offer for every customer, and one restaurant ran free delivery for every customer with no minimum. None offered free delivery above a basket amount.

### Products

- A dish's `options` bind it to choice groups defined beside the items; `multi_choice_config.total_range.min` says how many choices are obligatory. A "Khachapuri set" listed at 2.00 needs three choices at 15.00 each. The adapter adds the cheapest obligatory choices and states them at checkout.
- A weighed item carries `sell_by_weight_config` with `price_per_kg` and `grams_per_step`; its `price` is the price per kilogram and its stock figure is in grams. It is bought in whole steps.
- `unit_info` gives the pack size, and at some stores belongs to another product (a pack of fifteen eggs labelled 400 g). The adapter reads the size from the name first.

## Glovo

The API refuses requests without most of the web client's `glovo-*` headers (the adapter sends the set that worked), and store calls need the city and country codes, which `GET /v3/addresslookup/pub/coordinates` returns for a coordinate pair. The delivery point travels in headers. Bursts are answered with `429`.

| Purpose | Call |
|---|---|
| Stores and matching products | `POST /v1/web/store_wall/search?searchQuery=`, optionally `&categoryId=` (1 is restaurants and 4 groceries; 3 and 22 also occur on store cards) |
| One store | `GET /v3/stores/{slug}?includeClosed=true&includeDisabled=false` |
| Items in one store | `GET /v3/stores/{id}/addresses/{addressId}/search?query=` |
| Small-basket surcharge | `GET /v1/stores/{id}/addresses/{addressId}/node/store_fees` |

The search answers with a screen description: a card per store, followed by a row of that store's matching products with display prices. A store's open state and category sit in the card's display-tracking event.

Fee parameters as published, for a supermarket (SPAR): delivery 1.49 lari; `serviceFeeInfo` of `setupValue` 9 with `minValue` 229 and `maxValue` 699; one surcharge range from 0 to 30 lari of 2.99 lari with strategy `CAPPED`. A restaurant showed 9 / 129 / 499 and a 1.99 surcharge below 15 lari.

- The **surcharge** is the gap up to the range's end, at most the stated amount. A guest basket's own footer (`GET /v2/guest/customers/{id}/stores/{storeId}/addresses/{addressId}/mbs/footer`) gave 2.99 on a basket of 11.20 and 2.00 on one of 28.00, against a threshold of 30.00.
- The **service fee** is read as that percentage between the two bounds. This has not been checked against a priced order: the call that prices one, `POST /v3/checkouts/order/1/template`, needs a signed-in customer.
- The **delivery price** moves with demand and weather: the same store and point showed 1.49 at night and 4.99 in the afternoon.

A product's `promotion.price` is its discounted price; `promotion.isPrime` marks a subscriber-only price, which the adapter leaves out of the total. Products carry no size apart from their name and no mark for goods sold by weight. Store pages live at `glovoapp.com/en/{country}/{city}/stores/{slug}`.

A store's `promotions` were of four kinds across some thirty stores and restaurants: `FREE_DELIVERY` "on the first order" at every one of them; `FLAT_PRODUCT` and `PERCENTAGE_DISCOUNT` on "select items", some of the latter "with Prime"; and, at one restaurant, `BASKET_PERCENTAGE` on the "whole menu" with a `minimumBasketSizeCents` of 4000. The adapter counts the last kind, when it is not for Prime members, as that percentage off a basket of at least that size. This reading is unchecked.

## Bolt Food

Calls go to `deliveryuser.live.boltsvc.net/deliveryClient/public/{method}` with a query string naming the web client and a random device id; no other header is needed. A reply carries `code: 0` on success.

| Purpose | Call |
|---|---|
| Providers matching a query | `POST deliverySearch` with `search_tab_id` of `stores` or `restaurants` |
| Matching items in those providers | `POST getProviderPreviewMenuItems` with the provider ids, twenty at a time |
| Items in one provider | `GET searchInMenu?provider_id=&search_string=` |
| One provider | `POST getProviderOverview` |

Prices are decimal lari, for the pack as named. `selling_unit` of `kg` does not mean the price is per kilogram: a "Gouda briquette 100 g" at 4.50 carries `unit_price` "45,00 ₾/kg" beside it. The two together give the pack's weight. `option_group_presence` other than `none` marks a dish with choices.

An anonymous visitor gets the delivery price and nothing more. `getProviderFeeDisclosure` lists a small order fee, a service fee and a packaging fee by name and ends "Sign in to see fee estimates", and `min_price_details` was empty in every menu read. Bolt totals from the adapter are therefore lower bounds.

Provider pages live at `food.bolt.eu/en-US/{city_id}/p/{slug}`.

## Subscriptions

As the platforms describe them on their own pages; none of it is computed.

- **Wolt+** (`explore.wolt.com/en/geo/wolt-plus`): 8.99 lari a month. No delivery fee at venues marked W+, within 4 km, on baskets from 15 lari at restaurants, 20 at retailers and 35 at grocery stores. Up to 80% off the service fee, more the nearer the venue. Stores sampled in Tbilisi carried `show_wolt_plus: false` for an anonymous visitor.
- **Glovo Prime** (`glovoapp.com/en/ge/tbilisi/glovo-prime`): 8.99 lari a month. "Unlimited free deliveries" at Prime restaurants, supermarkets and shops, and "lower fees on every order"; no figures. Stores report `primeAvailable`.
- **Bolt Plus** (`bolt.eu/en-ge/plus/`): free delivery with Bolt Food at venues carrying its logo, up to a maximum saving per order and above a minimum order, both unstated for Georgia.

## Signed-in access

None of it has been exercised with an account. What the web clients show:

- **Wolt**: the checkout call accepts a bearer token, and the dynamic store call has subscription fields (`delivery_pricing_with_subscription`, `subscription.active_plan_id`) that are empty for an anonymous visitor. Per the wolt-mcp source, a basket is written with `POST /order-xp/v1/baskets` (a whole-basket replace keyed by store id) and the access token is refreshed at `authentication.wolt.com/v1/wauth2/access_token`.
- **Glovo**: sign-in by e-mail and password is plain HTTP with no captcha: `POST /oauth/token` with `{grantType: "password", username, password}` after registering a device at `POST /identity/v4/devices`; the token then travels as a bare `Authorization` value and is renewed at `POST /oauth/refresh`. A wrong password answered `401`. The phone route and any second step carry a reCAPTCHA token. `GET /customers/{id}/subscription/status` reports Prime. A guest basket was read, written (`PUT /v2/guest/customers/{id}/baskets/{basketId}` with the whole basket) and deleted; the signed-in calls drop `guest/customers/{id}` from the path. `POST /v3/checkouts/order/1/template` builds the priced checkout screen without ordering; the calls beside it without `/template` place an order.
- **Bolt Food**: the bundle pairs public calls with signed-in twins that drop `/public` from the path (seen for `searchInMenu` and `getMenuDishes`), and carries basket services (`fetchActiveBasket`, `DeliveryBasketService`).
