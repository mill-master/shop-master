# shop-master

Find the cheapest way to get a whole shopping list delivered in Tbilisi. Tell Claude what you need. It prices the list on Wolt, Glovo and Bolt Food, store by store, with delivery, service and small-order fees included, and names the store, or the split between two stores, that costs least. It compares a restaurant dish the same way.

## Why

Each of the three apps sells through separate stores, and every order pays its own delivery and service fee, plus a small-order fee when the basket is under the store's minimum. The apps search one product at a time. A list of five items therefore ends in a store that has four of them and a second order for the fifth with a second set of fees, or in a basket padded with things you did not want. The cheapest shelf price is rarely the cheapest order.

## Install

In Claude Code:

```
/plugin install shop-master --marketplace mill-master/shop-master
```

On a Claude Code older than 2.1.275, add the marketplace first: `/plugin marketplace add mill-master/shop-master`, then `/plugin install shop-master@shop-master`.

It needs Python 3 and nothing else: no account on any platform, no API key, no packages.

## Use

Tell Claude once where deliveries go, as coordinates from a maps app: "my delivery point is 41.6938, 44.8015". Then ask in plain words:

- "I need two litres of milk, twenty eggs, bread, a kilo of rice and black pepper. Where should I order?"
- "Paracetamol and a phone charger, delivered now. What is the cheapest way?"
- "Compare a chicken shawarma across the apps. What comes with it, and which is nearest?"

or run `/shop-master:shop-master`.

Claude searches the three platforms, works out which product on each shelf is the one you meant and how many packs your amount comes to, and answers with the store or stores, what goes in each basket, the total with every fee, and links for checking out in the app. The arithmetic underneath looks like this, for milk, bread and paracetamol (store links left out):

```
4. about 21.47 in 2 orders, everything covered  [best with every fee known]
   g1  Glovo · Goodwill · open · 100m · rating 98%
      milk: 1 × სანტე რძე 2.5% 1 ლ./4860051001298 [1 l]  3.75
      bread: 1 × ბატონი ქართო დაჭრილი  1.65
      goods 5.40 + Delivery 0.99 + Service fee 2.29 + Small order fee 2.99 = 11.67  (fees and offers are computed from Glovo's published parameters, not priced by Glovo)
   w4  Wolt · Aversi Opera · open · 25-35 min · 970 m · rating 9.8
      paracetamol: 1 × პარაცეტამოლი 0.5გ #20ტ [0.5 g]  4.26
      goods 4.26 + Small order fee 2.99 + Service fee 1.00 + Delivery (970 m) 1.55 = 9.80  (priced by Wolt)
```

When no store has everything, it finds the division between two stores that costs least, moving an item to the dearer shelf where that lifts a basket over a fee threshold. A list that mixes groceries with a pharmacy or household item gets a store for each kind.

## How far to trust a total

| Platform | Total is | Because |
|---|---|---|
| Wolt | exact | Wolt prices any basket for an anonymous visitor, and the tool asks it, the store's campaigns included. |
| Glovo | "about" | It is computed from the delivery price, service-fee percentage and small-basket surcharge Glovo publishes for each store. Glovo itemises a basket's fees only after sign-in, so the service fee is unchecked. |
| Bolt Food | "at least" | Bolt shows only the delivery price before sign-in. Its service, small-order and packaging fees are missing from the total, so Bolt looks cheaper than it is. |

For that reason the best plan made only of fully known fees is always shown beside the cheapest-looking ones. A store's offers that are open to every customer, such as "GEL10 off on orders over GEL60", are counted. Prices, stock and opening hours are those of the moment of the search; delivery prices in particular move through the day.

## What it does not do

- It does not order, pay, or fill a cart. You check out in the app.
- It does not know your account. New-customer offers and subscriber prices are listed where a platform advertises them and left out of the totals. With Wolt+, Glovo Prime or Bolt Plus you pay less on that platform than shown, by up to the delivery fee and most of the service fee; Claude will say which way that tilts a close comparison, and cannot compute it without a signed-in session, which is not built.
- It was built and tested in Tbilisi. Other cities where these platforms operate are untried.

## The platforms' terms

Shop Master reads the private web interfaces that the platforms' own sites use. Wolt's terms forbid "bots or other automated methods" and access other than through its app and website, and Bolt Food's forbid "any automated collection of data" from its platform; Glovo's terms were not readable. Using this tool is therefore against at least two of the three, and you use it at your own risk. It asks for little: one comparison is on the order of a hundred paced requests, it waits when a platform throttles it, and it does not retry a refusal. The interfaces can change without notice. The project is not affiliated with Wolt, Glovo or Bolt.

[skills/shop-master/platforms.md](skills/shop-master/platforms.md) records how each platform is read and how its fee rules were measured.

## Development

`python3 -m unittest discover -s tests` runs the tests, which need no network. `claude --plugin-dir .` loads the plugin from a checkout, and the command-line tool runs by hand: `bin/shopmaster --help`.

Released under the MIT licence.
