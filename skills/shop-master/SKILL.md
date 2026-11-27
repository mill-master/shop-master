---
name: shop-master
description: "Someone in Tbilisi wants groceries, pharmacy or household items, or a restaurant dish delivered and asks where to order: prices the whole list on Wolt, Glovo and Bolt Food with delivery, service and small-order fees included, and names the store, or the split between stores, that costs least. Triggers: shopping list, order groceries, cheapest delivery, which app is cheaper, compare Wolt Glovo Bolt, small order fee, minimum order, free delivery threshold, best price for a dish."
---

# Shop Master

## The problem

Wolt, Glovo and Bolt Food each sell through separate stores, and an order belongs to one store. Every order pays its own delivery fee and service fee, and a basket below the store's minimum pays a small-order fee as well. The apps search one product at a time, so a shopper with five items finds a store for the first four, a second store for the fifth, and pays a second set of fees on a basket too small to clear its minimum, or pads that basket with things they did not want.

The cheapest shelf price therefore says little. What the shopper needs is the store where the whole list costs least once fees are counted, and, when no store has everything, the division of the list between stores that keeps each basket's fees lowest. The same holds for a restaurant dish: the menu price is one term of the total.

## The tool

`shopmaster` does the collecting and the arithmetic. It reads the three platforms the way their web sites do, without an account. It does not order, pay, or touch a cart: the shopper checks out in the app, from the links it prints. Run it as `python3 "${CLAUDE_PLUGIN_ROOT}/bin/shopmaster"` (`python` on Windows); the lines below write `shopmaster` for that, and `--help` on it and on each command gives the full syntax. One run goes:

```
shopmaster where                      # the saved delivery point
shopmaster gather --want 'milk=milk 1l' --want 'eggs*2=eggs|კვერცხი' --want 'rice=rice'
shopmaster pick w1.milk=3 g2.eggs=2x1 b1.rice=-
shopmaster solve
```

`gather` searches each platform for every wanted item, takes the stores that matched most of the list, and prints each store with its fee rules and up to eight candidate products per item. A `--want` is `key=query`, with `*N` after the key for a quantity and `|` between alternative queries; keys are plain words. `--food` turns the run to restaurants and dishes. `--add` extends the last run with more wants or with `--store platform:key`, and retries lookups that failed. `pick` says which candidate stands for an item at a store (`=3`), with a quantity that overrides the list's for that store (`=3x2`), or that nothing there fits (`=-`). `drop` removes a store. `solve` ranks the ways to buy the list using at most two orders (`--max-stores` changes that) and prints the best few plus the best single order.

The delivery point is a pair of coordinates saved with `where LAT LON label`. Fees and store choice depend on it, so when none is saved, or the order is going somewhere else, ask for it. A home address is personal: take coordinates from the shopper, or a landmark they name, in preference to sending their address to a geocoding service.

## Where your judgment is needed

The tool cannot tell what a product is. Everything below is yours.

**Queries.** The catalogues are Georgian, with English names machine-translated on Wolt and Bolt and absent on Glovo. English queries work on all three; a Georgian alternative after `|` recovers what a translation missed. Search for the product as a shelf label would name it, with the size when the shopper gave one.

**Candidates.** The starred candidate is only the platform's first hit, and it is often wrong: almond milk for milk, a chocolate egg for eggs, baby formula for milk at a pharmacy. Before a plan reaches the shopper, read the candidates of every item in it and pick the product that answers the request. Pick comparable products across stores, since a plan is only cheaper if it buys the same thing: one litre against 950 ml, ten eggs against fifteen. Where pack sizes differ, set the quantity per store. An item sold by weight is priced per kilogram and its quantity is a weight, so `tomatoes*0.5` buys half a kilogram. Where the shopper left the choice open, choose as a sensible shopper would and say what you chose; ask only when the options differ enough to change what they would buy.

**Stores.** Stores are chosen by how many of the items their search matched, loosely. A pharmacy matches "milk", "rice" and "bread" with baby food. Drop stores that do not belong to the list, and add better ones from the "also matched" lines at the end of `gather`, which name the next stores in each platform's ranking. Bolt Food has few grocery stores in Tbilisi and its matches deserve this check most.

**Then solve again.** Picks change prices, and prices change which division wins. Present a plan only after a `solve` that followed your last pick.

## Reading a plan

Each basket line ends with where its fees came from, and the plan's total is worded to match.

- A plain total is **priced by Wolt**: Wolt prices any basket for an anonymous visitor, so these fees are the ones checkout will show, bag charge included.
- **about** marks a Glovo basket. Glovo publishes a store's delivery price, its service-fee percentage with bounds, and its small-basket surcharge, and prices a real basket only after sign-in. The fees are computed from those published numbers.
- **at least** marks a Bolt Food basket. Bolt shows an anonymous visitor the delivery price alone; its service, small-order and packaging fees appear after sign-in. The real total is higher by an amount the tool cannot see. A Bolt plan that leads by a lari or two has not shown itself cheaper, and the shopper should hear that.

"N more goods here would cut the fees by M" appears under a basket that sits below a threshold. When M is close to N, something the shopper needs anyway is nearly free and worth suggesting; when M is small, paying the fee is cheaper than padding the basket.

A plan with two orders is listed only when it saves money over its own stores used alone or covers more of the list. A plan that leaves items out says WITHOUT and ranks below every plan that covers more.

Lines beginning `offer:` are deals the store advertises that the totals leave out, because most belong to new customers or subscribers. Mention one when it would change the answer for this shopper. `caveat:` and `!` lines are the tool telling you what it could not establish; a failed lookup means unknown, not absent.

A closed store is left out of `solve` unless `--closed` is given, which suits an order planned for later.

## Dishes

With `--food` the candidates are dishes, each with the restaurant's description beneath it. Portions, meats and sides differ under one name, so compare what arrives: a wrap against a box with fries, 350 g against 470 g. The store line gives delivery time, distance and rating, which matter more for a meal than for a bag of rice. Wolt's ratings run to 10, Bolt's to 5, and Glovo's are a percentage.

## What to tell the shopper

Lead with the recommendation: the store or stores, what goes in each basket, the total with its fees, and the links. Give product names so they can be found in the app, in English where the catalogue is Georgian. Add the runner-up when it is close or trades money for speed or certainty. Say what you substituted or assumed, and what is uncertain in the total. Amounts are in lari.

Prices, stock and opening state are as of the run's time, printed at the top of every report. Gather again for a decision made later.

## When something breaks

The platforms' web interfaces are private and change without notice. An adapter that starts failing names the call that failed. [platforms.md](platforms.md) records, for each platform, the calls in use, what each was verified to return, the fee measurements behind the rules, and what remains unverified, including what is known of signed-in access.
