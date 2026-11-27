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
shopmaster gather --want 'milk*2l=milk 1l' --want 'eggs*20pc=eggs|კვერცხი' --want 'rice*1kg=rice' --want 'bread=bread'
shopmaster pick w1.milk=3 g2.eggs=2x1 b1.rice=-
shopmaster solve
```

`gather` searches each platform for every item, reads the stores that matched most of the list plus a store for any item those lack, and prints each store with its fee rules and the best few candidate products per item. An item is `key=query`, with `|` between alternative queries; keys are plain words. After `*` comes how much: an amount with its unit (`20pc`, `2l`, `1kg`, `300g`), from which the tool counts the packs at each store, or a bare number of packs. `--food` turns the run to restaurants and dishes. `--add` extends the last run with more items or with `--store platform:key`, and retries whatever failed. `pick` says which candidate stands for an item at a store (`=3`), how many of it to buy (`=3x2`), or that nothing there fits (`=-`). `drop` removes a store. `solve` ranks the ways to buy the list using at most two orders (`--max-stores` changes that).

The delivery point is a pair of coordinates saved with `where LAT LON label`. Fees and store choice depend on it, so when none is saved, or the order is going somewhere else, ask for it. A home address is personal: take coordinates from the shopper, or a landmark they name, in preference to sending their address to a geocoding service.

## Where your judgment is needed

The tool cannot tell what a product is. Everything below is yours.

**Queries.** The catalogues are Georgian, with English names machine-translated on Wolt and Bolt and absent on Glovo. English queries work on all three; a Georgian alternative after `|` recovers what a translation missed. Search for the product as a shelf label would name it, with the size when the shopper gave one.

**How much.** Give the amount the shopper named, in their units: "twenty eggs" is `eggs*20pc`, and the tool turns it into two packs of ten or two of fifteen as each store sells them. A pack up to a tenth short counts as the size asked, since 950 ml and 900 g packs are sold as the litre and the kilo. Pack sizes are read from product names, so check the count the candidate line shows (`→ ×2`) against the name: a mislabelled product gives a wrong count. A candidate whose size cannot be read is marked "size unknown" and stands for nothing until you give the number to buy with `pick`.

**Candidates.** The starred candidate is only the platform's first match, and it is often wrong: almond milk for milk, a chocolate egg for eggs, baby formula for milk at a pharmacy. Before a plan reaches the shopper, read the candidates of every item in it and pick the product that answers the request, comparable across stores, since a plan is only cheaper if it buys the same thing. A price marked "from" belongs to a dish or product with choices to make; it includes the cheapest obligatory ones where the platform lists them, and the shopper's own choices can raise it. Where the shopper left the choice open, choose as a sensible shopper would and say what you chose; ask only when the options differ enough to change what they would buy.

**Stores.** Stores are chosen by how many of the items their search matched, loosely. A pharmacy matches "milk", "rice" and "bread" with baby food. Drop stores that do not belong to the list, and add better ones from the "also matched" lines at the end of `gather`, which name the next stores in each platform's ranking. Bolt Food has few grocery stores in Tbilisi and its matches deserve this check most.

**Other kinds of store.** Anything that is not a restaurant counts as a store, so pharmacy, pet, electronics and household items go in the same run as groceries. A list that mixes kinds seldom fits one store; the two-order plans are then the ones that matter, and `gather` reads a store for each kind.

**Then solve again.** Picks change prices, and prices change which division wins. Present a plan only after a `solve` that followed your last pick.

## Reading a plan

Each basket line ends with where its fees came from, and the plan's total is worded to match.

- A plain total is **priced by Wolt**: Wolt prices any basket for an anonymous visitor, so the goods, the fees and the store's offers are the ones checkout will show a returning customer.
- **about** marks a Glovo basket. Glovo publishes a store's delivery price, its service-fee percentage with bounds, and its small-basket surcharge, and prices a real basket only after sign-in. The fees are computed from those published numbers. Glovo raises delivery prices with demand and weather, so an hour-old run can be out by a few lari.
- **at least** marks a Bolt Food basket. Bolt shows an anonymous visitor the delivery price alone; its service, small-order and packaging fees appear after sign-in. The real total is higher by an amount the tool cannot see, so Bolt ranks cheaper than it is.

Because of that last point `solve` always lists the plan marked "best with every fee known" beside the cheapest-looking ones. When a Bolt plan leads it by less than a few lari, the known plan is the safer recommendation, and the shopper should hear why.

"N more goods here would cut the fees by M" appears under a basket that sits just below a threshold, when at least half of what the extra goods cost would come back in lower fees. Something the shopper needs anyway is then nearly free and worth suggesting.

A plan with two orders is listed only when it saves money over its own stores used alone or covers more of the list. A plan that leaves items out says WITHOUT and ranks below every plan that covers more.

Lines beginning `offer:` are the deals a store advertises. One marked "counted in the totals" is open to every customer and depends only on the basket's size, so the arithmetic includes it. On Wolt every campaign open to a returning customer is also put to Wolt's own pricing of the finished basket, and a product's campaign discount already shows in its candidate price, with the old price after "was" or the number of units it needs. The rest are left out because they belong to new customers or subscribers; mention one when it would change the answer for this shopper.

Free delivery above a basket amount, for a customer with no subscription, was not on offer at any store sampled on the three platforms in November 2026. It comes with the subscriptions:

- **Wolt+** (8.99 lari a month): no delivery fee at venues with the W+ badge within 4 km, on baskets from 15 lari at restaurants, 20 at shops and 35 at grocery stores, and up to 80% off the service fee.
- **Glovo Prime** (8.99 lari a month): free delivery at Prime stores and lower fees; Glovo states no figures.
- **Bolt Plus**: free delivery up to a cap per order above a minimum order; Bolt states no figures for Georgia.

The totals are those of a customer with none of these. A shopper who holds one pays less on that platform than shown, by up to the whole delivery fee and most of the service fee, which can change which plan wins. Ask whether they subscribe when two platforms are close, and say which way it tilts.

`caveat:` and `!` lines are the tool telling you what it could not establish. A failed lookup or store read means unknown, not absent, so settle it before answering: run `gather --add`, which tries again whatever failed, until those lines are gone. Report a gap to the shopper only when it survives that, with its reason.

A closed store is passed over for the next in the ranking, and left out of `solve`, unless `--closed` is given, which suits an order planned for later.

## Dishes

With `--food` the candidates are dishes, each with the restaurant's description beneath it. Portions, meats and sides differ under one name, so compare what arrives: a wrap against a box with fries, 350 g against 470 g. `solve` ranks by cost alone. The store line gives delivery time, distance and rating, which matter more for a meal than for a bag of rice, so name the nearest or quickest option beside the cheapest when they differ. Wolt's ratings run to 10, Bolt's to 5, and Glovo's are a percentage.

## What to tell the shopper

Lead with the recommendation: the store or stores, what goes in each basket, the total with its fees, and the links. Give product names so they can be found in the app, in English where the catalogue is Georgian. Add the runner-up when it is close or trades money for speed or certainty. Say what you substituted or assumed, and what is uncertain in the total. Amounts are in lari.

Prices, stock and opening state are as of the run's time, printed at the top of every report. Gather again for a decision made later. Prices in the apps can differ from the same shop's shelf prices, and goods sold by weight are charged by the weight actually packed.

## When something breaks

The platforms' web interfaces are private and change without notice. A failure names the platform's host and the call that failed. A platform that answers 429 is throttling: the tool waits and tries again by itself, and when lookups still fail with 429, a minute's pause before `gather --add` lets that platform recover. [platforms.md](platforms.md) records, for each platform, the calls in use, what each was verified to return, the fee measurements behind the rules, and what remains unverified, including what is known of signed-in access.
