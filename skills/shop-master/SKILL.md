---
name: shop-master
description: "Someone wants groceries, pharmacy or household items, or a restaurant dish delivered and asks where to order, anywhere Wolt, Glovo or Bolt Food deliver: prices the whole list on those platforms with delivery, service and small-order fees included, and names the store, or the split between stores, that costs least. Triggers: shopping list, order groceries, cheapest delivery, which app is cheaper, compare Wolt Glovo Bolt, small order fee, minimum order, free delivery threshold, best price for a dish."
---

# Shop Master

## The problem

Wolt, Glovo and Bolt Food each sell through separate stores, and an order belongs to one store. Every order pays its own delivery fee and service fee, and a basket below the store's minimum pays a small-order fee as well. The apps search one product at a time, so a shopper with five items finds a store for the first four, a second store for the fifth, and pays a second set of fees on a basket too small to clear its minimum, or pads that basket with things they did not want.

The cheapest shelf price therefore says little. What the shopper needs is the store where the whole list costs least once fees are counted, and, when no store has everything, the division of the list between stores that keeps each basket's fees lowest. The same holds for a restaurant dish: the menu price is one term of the total.

## The tool

`shopmaster` does the collecting and the arithmetic. It reads the three platforms the way their web sites do. It does not order, pay, or touch a cart: the shopper checks out in the app, from the links it prints. Run it as `python3 "${CLAUDE_PLUGIN_ROOT}/bin/shopmaster"` (`python` on Windows); the lines below write `shopmaster` for that, and `--help` on it and on each command gives the full syntax.

Fees and store choice depend on where the order is going, so a delivery point comes first: a pair of coordinates saved with `shopmaster where LAT LON label`, and shown by `where` alone. When none is saved, or the order is going somewhere else, ask for it. A home address is personal: take coordinates from the shopper, or use those of a landmark they name, in preference to sending their address to a geocoding service.

Before every request the shopper chooses how it is run: signed in, which uses the accounts they have signed in to, or signed out. The tool gathers nothing until that choice is made. Run `gather` first without either choice: it asks no platform anything, prints which platforms are signed in, how each was signed in, and what each way changes, and stops. Put that choice to the shopper in your own words, with what a signed-out run cannot do, and run `gather` again with their answer. Ask for each new request, also when they answered before, and leave the choice to them: it is their account. A request that itself says how to run it has made the choice. `gather --add` continues a run the way it was chosen.

A run starts with `gather`, which takes the shopper's choice and one `--want` for each item:

```
shopmaster gather --signed-out --want 'milk*2l=milk 1l' --want 'eggs*20pc=eggs|კვერცხი' --want 'bread=bread'
```

An item is `key=query`, with `|` between alternative queries. The key is a plain word of your choosing, by which the item is named from then on. After `*` comes how much: an amount with its unit (`20pc`, `2l`, `1kg`, `300g`), from which the tool counts the packs at each store, or a bare number of packs, and with nothing one pack. `--food` turns the run to restaurants and dishes.

`gather` searches each platform for every item, reads the stores of each platform that matched most of the list (three, unless `--per-platform` says otherwise) plus a store for any item those lack, saves what it found as the run, and prints it with a block for each store:

```
w1  Wolt · Carrefour Mtatsminda · open · 55-65 min · 480 m · rating 9.0
    https://wolt.com/ka/geo/tbilisi/venue/carrefour-vekua
    fees (Delivery, Service fee, Small order fee, Bag) by basket: 10.00→6.33  25.00→3.34  50.00→5.34  100.00→6.33
    milk  *1  Sante milk 1 l  [1 l]  4.59 (4.59/l), was 4.90  at most 3 an order  → ×2
           2  Satnali almond milk 1 l  [1 l]  12.29 (12.29/l), was 14.45  → ×2
           3  Village Nobati Milk 3.2% 900g  [900 g]  5.10 (5.67/kg)  → sized in another unit
           4  Mila milk 3.2%-1l  [1 l]  5.95 (5.95/l)  → ×2
```

`w1` is the tool's name for that store: the platform's initial and a number. The fees line gives what the store's fees come to together at four sizes of basket: here 6.33 on goods of 10.00, and 3.34 on 25.00, where the small-order fee has gone. Under each item its first few candidates are numbered. The one with `*` before its number is the one that stands for the item at that store, and `→ ×2` is how many packs the amount asked comes to. After the stores come "also matched" lines, which name further stores as `platform:key`, and a line beginning `!` for anything that failed.

The other commands work on the saved run:

```
shopmaster pick w1.milk=4 g2.eggs=2x1 b1.bread=-
shopmaster drop b2
shopmaster gather --add --store wolt:spar-amaghleba --want 'rice*1kg=rice'
shopmaster show w1
shopmaster solve
```

`pick` changes what stands: `w1.milk=4` makes candidate 4 stand for milk at `w1`, `g2.eggs=2x1` makes it candidate 2 and buys one of it whatever amount was asked, and `b1.bread=-` says nothing there fits. `drop` removes a store. `gather --add` extends the run with a store, named as an "also matched" line names it, or with more items, and tries again whatever failed. `show` prints the run again, or one store of it. `solve` ranks the ways to buy the list using at most two orders (`--max-stores` changes that); the section on reading a plan shows its report.

The tool works wherever one of the three platforms delivers. A platform that is not at the delivery point says so in one line and is left out of the run. It was built and measured in Tbilisi and has also been run in other countries; what a total's wording means (plain, "about", "at least") holds everywhere, while a remark below that names Tbilisi or an amount in lari is a local observation.

## Where your judgment is needed

The tool cannot tell what a product is. Everything below is yours.

**Queries.** A catalogue is written in its country's language. Wolt and Bolt add English names in some countries, machine-translated in Georgia, and Glovo has none. Give the local word and an English alternative after `|`: in Tbilisi English finds most things on all three and the Georgian word recovers what a translation missed, and in the other cities tried the local word (`mleko`, `молоко`, `leche`) was the one that found the product. Search for the product as a shelf label would name it, with the size when the shopper gave one.

**How much.** Give the amount the shopper named, in their units: "twenty eggs" is `eggs*20pc`, and the tool turns it into two packs of ten or two of fifteen as each store sells them. A pack up to a tenth short counts as the size asked, since 950 ml and 900 g packs are sold as the litre and the kilo. Pack sizes are read from product names, so check the count the candidate line shows (`→ ×2`) against the name: a mislabelled product gives a wrong count. A candidate whose size cannot be read is marked "size unknown", and one sized in another kind of unit than the amount asked (grams for litres) says so; neither stands for the item until you give the number to buy with `pick`.

**Candidates.** Left alone, the starred candidate is only the platform's first match, and it is often wrong: almond milk for milk, a chocolate egg for eggs, baby formula for milk at a pharmacy. Before a plan reaches the shopper, read the candidates of every item in it and pick the product that answers the request, comparable across stores, since a plan is only cheaper if it buys the same thing. A price marked "from" belongs to a dish or product with choices to make; it includes the cheapest obligatory ones where the platform lists them, and the shopper's own choices can raise it. Where the shopper left the choice open, choose as a sensible shopper would and say what you chose; ask only when the options differ enough to change what they would buy.

**Stores.** Stores are chosen by how many of the items their search matched, loosely. A pharmacy matches "milk", "rice" and "bread" with baby food. Drop stores that do not belong to the list, and add better ones from the "also matched" lines at the end of `gather`, which name the next stores in each platform's ranking. Bolt Food has few grocery stores in Tbilisi and its matches deserve this check most.

**Other kinds of store.** Anything that is not a restaurant counts as a store, so pharmacy, pet, electronics and household items go in the same run as groceries. A list that mixes kinds seldom fits one store; the two-order plans are then the ones that matter, and `gather` reads a store for each kind.

**Then solve again.** Picks change prices, and prices change which division wins. Present a plan only after a `solve` that followed your last pick.

## Reading a plan

`solve` prints the plans, cheapest first among those that cover the most:

```
Run gathered 2026-11-27T18:09+04:00 for Freedom Square, signed out; amounts in GEL

1. 23.10 in 1 order, everything covered  [best single order; best with every fee known]
   w2  Wolt · Goodwill Galleria Tbilisi · open · 35-45 min · 130 m · rating 9.6
      https://wolt.com/ka/geo/tbilisi/venue/goodwill-galleria-tbilisi
      milk: 2 × Sante milk 2.5% 1 l. [1 l]  7.50
      eggs: 2 × "What is good" - egg white (10 pcs) - M-0 [10 pc]  10.50
      bread: 1 × Bread baguette of the highest quality  2.10
      goods 20.10 + Bag 0.60 + Service fee 1.61 + Delivery (130 m) 0.79 = 23.10  (priced by Wolt)

2. about 23.95 in 1 order, everything covered
   g2  Glovo · Carrefour · open · 500m · rating 96%
      https://glovoapp.com/en/ge/tbilisi/stores/1carrefour-tbi
      milk: 2 × სანტე რძე 1 ლ [1 l]  9.18
      eggs: 2 × ჩემი არჩევანი კვერცხი M თეთრი-10ც [10 pc]  7.10
      bread: 1 × იფქლი თეთრი პური ქართო დაჭრილი 470 გრ 1ც [470 g]  1.40
      goods 17.68 + Delivery 0.99 + Service fee 2.29 + Small order fee 2.99 = 23.95  (fees and offers are computed from Glovo's published parameters, not priced by Glovo)
```

A plan is one or two baskets, each at one store. A basket's last line adds its goods and fees and ends, in brackets, with where the fees came from, and the plan's total on its first line is worded to match.

- A plain total is **priced by Wolt**: Wolt prices any basket for an anonymous visitor, so the goods, the fees and the store's offers are the ones checkout will show a customer who has ordered before and holds no subscription.
- **about** marks a Glovo basket. Glovo publishes a store's delivery price, its service-fee percentage with bounds, and its small-basket surcharge, and prices a real basket only after sign-in. The fees are computed from those published numbers. Glovo's delivery price moves through the day (1.49 lari at night became 4.99 the next afternoon at one Tbilisi store), so an hour-old run can be out by more than the whole delivery fee.
- **at least** marks a Bolt Food basket. Bolt shows an anonymous visitor the delivery price alone; its service, small-order and packaging fees appear after sign-in. The real total is higher by an amount the tool cannot see, so Bolt ranks cheaper than it is.

Because of that last point `solve` always lists the plan marked "best with every fee known" beside the cheapest-looking ones. When a Bolt plan leads it by less than the service and small-order fees that the Wolt and Glovo stores of the same report charge on a basket of that size, the known plan is the safer recommendation, and the shopper should hear why.

"N more goods here would cut the fees by M" appears under a basket that sits just below a threshold, when at least half of what the extra goods cost would come back in lower fees. Something the shopper needs anyway is then nearly free and worth suggesting.

A plan with two orders is listed only when it saves money over its own stores used alone or covers more of the list. A plan that leaves items out says WITHOUT and ranks below every plan that covers more.

Lines beginning `offer:` are the deals a store advertises. One marked "counted in the totals" is open to every customer and depends only on the basket's size, so the arithmetic includes it. On Wolt every offer open to such a customer is also put to Wolt's own pricing of each basket in a plan, and a product under a store discount shows the discounted price as its candidate price, with the old price after "was", or says from how many units the discount applies. The rest are left out because they belong to new customers or subscribers; mention one when it would change the answer for this shopper.

A candidate line says when a store limits how many of a product one order may take, and `solve` says when the count wanted is above that limit or above the stock shown.

Free delivery above a basket amount, for a customer with no subscription, is rare: of some thirty stores sampled on Wolt in Tbilisi in November 2026 one offered it, and the totals count such an offer where a store runs one. As a rule it comes with the subscriptions, described here as each platform states them for Georgia; other countries have their own prices and thresholds:

- **Wolt+** (8.99 lari a month): no delivery fee at venues with the W+ badge within 4 km, on baskets from 15 lari at restaurants, 20 at shops and 35 at grocery stores, and up to 80% off the service fee.
- **Glovo Prime** (8.99 lari a month): free delivery at Prime stores and lower fees; Glovo states no figures.
- **Bolt Plus**: free delivery up to a cap per order above a minimum order; Bolt states no figures for Georgia.

The totals are those of a customer with none of these. A shopper who holds one pays less on that platform than shown, by up to the whole delivery fee and most of the service fee, which can change which plan wins. Ask whether they subscribe when two platforms are close, and say which way it tilts.

`caveat:` and `!` lines are the tool telling you what it could not establish. A failed lookup or store read means unknown, not absent, so settle it before answering: run `gather --add`, which tries again whatever failed. Run it again while that makes the lines fewer, and stop when a line says a platform is being left alone or has reached its hourly limit: the last section says what to do then. Report a gap to the shopper only when it survives that, with its reason.

A closed store is passed over for the next in the ranking, and left out of `solve`, unless `--closed` is given, which suits an order planned for later.

## The shopper's own account

Everything above works signed out. A run uses an account only when the shopper chose a signed-in run for that request, and then for one thing: each Wolt basket in the plans `solve` lists is priced as their account pays, Wolt+ and personal offers included, and its line ends "priced by Wolt for your account". Glovo and Bolt totals stay as described above in either kind of run. Searches, shelves and stores are read signed out in both, and no cart is filled on any platform, which the shopper should hear when they expect one to be. Apart from runs, `shopmaster account` reports who is signed in and whether a subscription shows there, and it asks the platforms in the shopper's name, so run it when they ask for it.

Before a shopper signs in, tell them that the platforms' terms forbid automated use and that an account used with this tool can be restricted; the platform notes named at the end of this file quote the clauses. For the same reason the tool asks little of an account: its requests are spaced seconds apart, none is repeated, and an hourly limit stops them. When a platform answers one with 429, which is throttling, the account is left alone for an hour, and when it answers 401 or 403, a refusal, until the shopper signs in again. Baskets are priced as a visitor's meanwhile, and the basket line says so.

Signing in takes a password or a code, which should not pass through this conversation, so the shopper runs the command in a terminal of their own. That terminal knows neither `shopmaster` nor any variable of yours: give them the whole line you would run yourself, with the folder's real path written out in it, ending in one of these.

- `login wolt --browser` or `login glovo --browser` opens a plain browser window at the platform's sign-in page. The shopper signs in there as usual and closes the browser, and the tool then reads the session out with the browser run headless, so no window opens again. This needs Google Chrome or Chromium and a desktop. It is the way that has worked: on 2026-11-27 one real account signed in to Wolt and to Glovo through it.
- `login wolt` asks for their phone number and then the code Wolt texts, or at an empty answer takes the link from a sign-in e-mail they request at wolt.com. On the one real try Wolt wanted a captcha before texting, at which the tool stops and names the browser window.
- `login glovo` asks for e-mail and password. An account opened with a phone number, Google or Apple has only the browser window.

Bolt Food is read signed out only. Its fraud protection refused the one sign-in tried with a real account, and the tool neither tries again nor looks for a way past it. When Bolt Plus could change the answer, ask the shopper whether they hold it.

The token stays in a file only they can read, and `logout PLATFORM` removes it. When a sign-in stops, pass the shopper the tool's message unaltered, since it says what to do next. As of 2026-11-27 no basket has yet been priced for a real account, so read the first signed-in totals with care and say so.

## Dishes

With `--food` the candidates are dishes, each with the restaurant's description beneath it. Portions, meats and sides differ under one name, so compare what arrives: a wrap against a box with fries, 350 g against 470 g. `solve` ranks by cost alone. The store line gives delivery time, distance and rating, which matter more for a meal than for a bag of rice, so name the nearest or quickest option beside the cheapest when they differ. Wolt's ratings run to 10, Bolt's to 5, and Glovo's are a percentage.

## What to tell the shopper

Lead with the recommendation: the store or stores, what goes in each basket, the total with its fees, and the links. Say whether the run was made signed in or signed out, which the first line of each report states. Give product names so they can be found in the app, with a translation where the catalogue is not in the shopper's language. Add the runner-up when it is close or trades money for speed or certainty. Say what you substituted or assumed, and what is uncertain in the total. Amounts are in the currency named on the first line of `solve`.

Prices, stock and opening state are as of the run's time, printed at the top of every report. Gather again for a decision made later. Prices in the apps can differ from the same shop's shelf prices, and goods sold by weight are charged by the weight actually packed.

## When something breaks

The platforms' web interfaces are private and change without notice. A failure names the platform's host and the call that failed.

The tool asks each platform at most once a second, and keeps that pace across runs: two runs started side by side take turns, so starting several gains nothing. A platform that answers 429 is throttling. The tool waits and tries again by itself, and when the platform keeps answering 429 it is left alone for ten minutes: lookups then fail at once, in this run and in later ones, with the time from which it may be asked again. The tool also limits how often it asks one platform in an hour, and past that limit a lookup fails in the same way. In either case answer now with the platforms that did reply: say which one is missing, and from what time it could be added with `gather --add` if the shopper wants it. Prefer that to holding the answer back, since two platforms now serve a shopper better than three in a quarter of an hour, and avoid asking sooner, which only adds to what the platform is refusing.

A run is refused with "Gather afresh" when it was saved by another version of the tool or for another delivery point; gather again. [platforms.md](platforms.md) records, for each platform, the calls in use, what each was verified to return, the fee measurements behind the rules, and what remains unverified, including what is known of signed-in access.
