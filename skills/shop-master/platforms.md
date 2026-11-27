# The three platforms, as read by the adapters

Everything here was observed on 2026-11-27 from a connection in Tbilisi, for a delivery point at Freedom Square (41.6938, 44.8015), without an account. Amounts are in tetri unless a field is marked as lari. Each platform's adapter (`lib/wolt.py`, `lib/glovo.py`, `lib/bolt.py`) holds the request details; this page holds what was learned that the code alone does not show.

## Connectors and MCP servers

- **Glovo** runs an official search-only MCP server at `https://api.glovoapp.com/discovery-mcp/mcp` (tools `search_products` and `render_products_carousel`). It answers `403 Forbidden` to local clients: a plain JSON-RPC `initialize`, the MCP inspector, and Claude Code's own HTTP client were all refused, while a nonexistent path beside it returns `404`. Glovo documents it only as a connector chosen inside Claude's Connectors settings. It returns products and store details and no fee rules, so the adapter reads the web client's calls instead.
- **Wolt** has no official server. Two unofficial ones exist, both built on the web client's calls and both able to fill a signed-in basket: `github.com/erlaufer/wolt-mcp`, and `github.com/mekedron/wolt-mcp`, which is the one listed at `mcpmarket.com/server/wolt`. The first one's source documents Wolt's token refresh and basket endpoints, and was read for the request headers used here; the second has not been examined. Neither is a dependency.
- **Bolt Food** has no MCP server or published consumer client that a search of GitHub and the MCP directories turned up. `developer.bolt.eu` documents the merchant side only.

## Wolt

Calls, all accepted from a plain HTTP client with the web client's headers and no cookies:

| Purpose | Call |
|---|---|
| Items across stores | `POST restaurant-api.wolt.com/v1/pages/search` with `{q, target: "items", lat, lon}`; up to 200 hits, each naming its store and a `product_line` such as `grocery`, `restaurant` or `pharmacy` |
| Items in one store | `POST consumer-api.wolt.com/consumer-api/consumer-assortment/v1/venues/slug/{slug}/assortment/items/search?language=en` with `{q}`; works for restaurants too |
| Store, fixed facts | `GET consumer-api.wolt.com/order-xp/web/v1/pages/venue/slug/{slug}/static` |
| Store, for a delivery point | `GET consumer-api.wolt.com/order-xp/web/v1/venue/slug/{slug}/dynamic/?lat=&lon=` |
| Price a basket | `POST consumer-api.wolt.com/order-xp/web/v2/pages/checkout` |

The checkout call is what makes Wolt exact. It prices a basket without login and without storing anything. It trusts the prices in the request and accepts an item id that does not exist, so a one-line basket of any subtotal reads the store's fees at that subtotal. Each line needs `id`, `count`, `base_price`, `end_amount`, `options`, `restrictions`, `exclude_from_discounts` and `category_id`. Passing the store's campaign ids in `use_promo_discount_ids` applies its offers, new-customer ones included, which is why the adapter passes none.

Fees measured through that call, at a grocery store (Wolt Market Baratashvili, minimum 2500) and a restaurant (minimum 1200):

- **Service fee**: 8% of the subtotal, floor 100, cap 499, at both. Checkout states the rule in its fee explanation.
- **Small order fee**: the gap up to the store minimum, capped at 399 for the grocery store and 299 for the restaurant. The cap appears nowhere in the store's published data.
- **Delivery**: one amount per store and delivery point, the same at every subtotal from 3 to 120 lari. It equals `delivery_specs.original_delivery_price` in the dynamic call.
- **Bag**: the store's `bag_fee` for every started ten items (40 per ten at the grocery store); none at the restaurant.

`delivery_specs.delivery_pricing.price_ranges` in the dynamic call gives the service fee as bands `a + b × subtotal`. Its first band falls as the basket grows (`b = -1`), which checkout does not charge: it charges the floor there. The adapter flattens that band; `tests/test_fees.py` holds both measured tables.

An anonymous visitor is shown new-customer offers ("GEL0 delivery fee", "GEL12 off on orders over GEL30"), marked as such only in their description text. The store page's displayed delivery price of zero comes from them.

Checkout applies the offers whose ids it is given and whose conditions the basket meets. A discount on the goods comes back as a lowered "Item subtotal" beside its original amount, and the service fee stays computed on the original. Measured: "10% off (up to GEL20) on orders over GEL50" took 6.00 off a 60.00 basket and 20.00 off a 300.00 one, and nothing off 40.00; "GEL50 off on orders over GEL200" took 50.00 off 250.00 and nothing off 150.00. Given a new-customer goods offer together with one for every customer, checkout applied one of the two, so offers on the goods do not add up.

Of some thirty stores and restaurants sampled, three ran an offer on the goods for every customer, and one restaurant ran free delivery for every customer with no minimum. None offered free delivery above a basket amount.

A weighed item carries `sell_by_weight_config` with `price_per_kg` and `grams_per_step`; its `price` is the price per kilogram and its stock figure is in grams.

## Glovo

The API refuses requests without most of the web client's `glovo-*` headers (the adapter sends the set that worked), and store calls need the city and country codes, which `GET /v3/addresslookup/pub/coordinates` returns for a coordinate pair. The delivery point travels in headers.

| Purpose | Call |
|---|---|
| Stores and matching products | `POST /v1/web/store_wall/search?searchQuery=`, optionally `&categoryId=` (1 is restaurants and 4 groceries; 3 and 22 also occur on store cards) |
| One store | `GET /v3/stores/{slug}?includeClosed=true&includeDisabled=false` |
| Items in one store | `GET /v3/stores/{id}/addresses/{addressId}/search?query=` |
| Small-basket surcharge | `GET /v1/stores/{id}/addresses/{addressId}/node/store_fees` |

The search answers with a screen description: a card per store, followed by a row of that store's matching products with display prices. A store's open state and category sit in the card's display-tracking event.

Fee parameters as published, for a supermarket (SPAR): delivery 1.49 lari; `serviceFeeInfo` of `setupValue` 9 with `minValue` 229 and `maxValue` 699; one surcharge range from 0 to 30 lari of 2.99 lari with strategy `CAPPED`. A restaurant showed 9 / 129 / 499 and a 1.99 surcharge below 15 lari. The adapter reads these as a 9% service fee between the two bounds and a surcharge equal to the gap up to the range's end, at most the stated amount. **Neither reading has been checked against a priced order**: the call that itemises a basket's fees, `/v1/stores/{id}/addresses/{addressId}/node/fees_breakdown`, answers `401 Missing auth token`.

A product's `promotion.price` is its discounted price; `promotion.isPrime` marks a subscriber-only price, which the adapter leaves out of the total. Store pages live at `glovoapp.com/en/{country}/{city}/stores/{slug}`.

A store's `promotions` were of four kinds across some thirty stores and restaurants: `FREE_DELIVERY` "on the first order" at every one of them; `FLAT_PRODUCT` and `PERCENTAGE_DISCOUNT` on "select items", some of the latter "with Prime"; and, at one restaurant, `BASKET_PERCENTAGE` on the "whole menu" with a `minimumBasketSizeCents` of 4000. The adapter counts the last kind, when it is not for Prime members, as that percentage off a basket of at least that size. This reading, too, is unchecked.

## Bolt Food

Calls go to `deliveryuser.live.boltsvc.net/deliveryClient/public/{method}` with a query string naming the web client and a random device id; no other header is needed. A reply carries `code: 0` on success.

| Purpose | Call |
|---|---|
| Providers matching a query | `POST deliverySearch` with `search_tab_id` of `stores` or `restaurants` |
| Matching items in those providers | `POST getProviderPreviewMenuItems` with the provider ids, twenty at a time |
| Items in one provider | `GET searchInMenu?provider_id=&search_string=` |
| One provider | `POST getProviderOverview` |

Prices are decimal lari. `selling_unit` of `kg` marks an item sold by weight.

An anonymous visitor gets the delivery price and nothing more. `getProviderFeeDisclosure` lists a small order fee, a service fee and a packaging fee by name and ends "Sign in to see fee estimates", and `min_price_details` was empty in every menu read. Bolt totals from the adapter are therefore lower bounds.

Provider pages live at `food.bolt.eu/en-US/{city_id}/p/{slug}`.

## Signed-in access

None of it has been exercised. What the web clients show:

- **Wolt**: the checkout call accepts a bearer token, and the dynamic store call has subscription fields (`delivery_pricing_with_subscription`, `subscription.active_plan_id`) that are empty for an anonymous visitor. Stores in Tbilisi carried `show_wolt_plus: false`. Per the wolt-mcp source, a basket is written with `POST /order-xp/v1/baskets` (a whole-basket replace keyed by store id) and the access token is refreshed at `authentication.wolt.com/v1/wauth2/access_token`.
- **Glovo**: the web bundle names `v1/authenticated/customers/{id}/baskets`, `v2/baskets/stores/{id}?storeAddressId=` and guest equivalents under `v2/guest/customers/{id}/`. Stores report `primeAvailable: true`.
- **Bolt Food**: the bundle pairs public calls with signed-in twins that drop `/public` from the path (seen for `searchInMenu` and `getMenuDishes`), and carries basket services (`fetchActiveBasket`, `DeliveryBasketService`).
