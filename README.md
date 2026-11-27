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

- "I need milk, eggs, bread, rice and black pepper. Where should I order?"
- "Paracetamol and a phone charger, delivered now. What is the cheapest way?"
- "Compare a chicken shawarma across the apps. What comes with it, and which is nearest?"

or run `/shop-master:shop-master`.

Claude searches the three platforms, works out which product on each shelf is the one you meant, and answers with the store or stores, what goes in each basket, the total with every fee, and links for checking out in the app. The arithmetic underneath looks like this:

```
1. about 25.26 in 1 order, everything covered
   g2  Glovo · Nikora Supermarket · open · 1.8km · rating 97%
      milk: 1 × რძე ულტრაპასტერიზებული 2.5% 1ლ სანტე  5.80
      ...
      goods 17.49 + Delivery 2.49 + Service fee 2.29 + Small order fee 2.99 = 25.26
      12.51 more goods here would cut the fees by 2.58

2. 29.50 in 1 order, everything covered
   w3  Wolt · VAKE BY SPAR Tsotne Dadiani · open · 35-45 min · 2.7 km · rating 9.2
      ...
      goods 21.58 + Bag 0.20 + Small order fee 1.90 + Service fee 1.73 + Delivery (2.7 km) 4.09 = 29.50  (priced by Wolt)
```

When no store has everything, it finds the division between two stores that costs least, moving an item to the dearer shelf where that lifts a basket over a fee threshold.

## How far to trust a total

| Platform | Total is | Because |
|---|---|---|
| Wolt | exact | Wolt prices any basket for an anonymous visitor, and the tool asks it. |
| Glovo | "about" | It is computed from the delivery price, service-fee percentage and small-basket surcharge Glovo publishes for each store. Glovo itemises a basket's fees only after sign-in, so the computation is unchecked. |
| Bolt Food | "at least" | Bolt shows only the delivery price before sign-in. Its service, small-order and packaging fees are missing from the total, so Bolt looks cheaper than it is. |

A store's offers that are open to every customer, such as "GEL10 off on orders over GEL60", are counted in its totals. Prices, stock and opening hours are those of the moment of the search.

## What it does not do

- It does not order, pay, or fill a cart. You check out in the app.
- It does not know your account. New-customer offers and subscriber prices are listed where a platform advertises them and left out of the totals, and what Glovo Prime, Wolt+ or Bolt Plus would change for you is not computed. That needs a signed-in session, which is not built.
- It was built and tested in Tbilisi. Other cities where these platforms operate are untried.

## The platforms' terms

Shop Master reads the private web interfaces that the platforms' own sites use, at a paced, low volume. Those interfaces can change without notice, and the platforms' terms may restrict automated reading: you use it at your own risk. The project is not affiliated with Wolt, Glovo or Bolt.

[skills/shop-master/platforms.md](skills/shop-master/platforms.md) records how each platform is read and how its fee rules were measured.

## Development

`python3 -m unittest discover -s tests` runs the tests, which need no network. `claude --plugin-dir .` loads the plugin from a checkout, and the command-line tool runs by hand: `bin/shopmaster --help`.

Released under the MIT licence.
