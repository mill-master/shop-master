# shop-master

Find the cheapest way to get a whole shopping list delivered. Tell Claude what you need. It prices the list on Wolt, Glovo and Bolt Food, the delivery apps, whichever of them deliver where you are, store by store, with delivery, service and small-order fees included, and names the store, or the split between two stores, that costs least. It compares a restaurant dish the same way.

## Why

Each of the three apps sells through separate stores, and every order pays its own delivery and service fee, plus a small-order fee when the basket is under the store's minimum. The apps search one product at a time. A list of five items therefore ends in a store that has four of them and a second order for the fifth with a second set of fees, or in a basket padded with things you did not want. The cheapest shelf price is rarely the cheapest order.

## Install

In Claude Code:

```
/plugin install shop-master --marketplace mill-master/shop-master
```

On a Claude Code older than 2.1.275, add the marketplace first: `/plugin marketplace add mill-master/shop-master`, then `/plugin install shop-master@shop-master`.

It needs Python 3 and nothing else: no account on any platform, no API key, no packages. Signing in, which is optional, can also need Google Chrome or Chromium.

## Use

Tell Claude once where deliveries go, as coordinates from a maps app: "my delivery point is 41.6938, 44.8015". It is kept on your computer for later requests. Then ask in plain words:

- "I need two litres of milk, twenty eggs, bread, a kilo of rice and black pepper. Where should I order?"
- "Paracetamol and a phone charger, delivered now. What is the cheapest way?"
- "Compare a chicken shawarma across the apps. What comes with it, and which is nearest?"

or run `/shop-master:shop-master`.

Claude searches the three platforms, works out which product on each shelf is the one you meant and how many packs your amount comes to, and answers with the store or stores, what goes in each basket, the total with every fee, and links for checking out in the app. Behind that answer is the tool's own report, in which each way of buying the list is a numbered plan. This one, from Tbilisi and in lari, splits milk, bread and paracetamol between a Glovo store and a Wolt pharmacy, which the tool calls g1 and w4 (store links left out):

```
4. about 21.47 in 2 orders, everything covered  [best with every fee known]
   g1  Glovo · Goodwill · open · 100m · rating 98%
      milk: 1 × სანტე რძე 2.5% 1 ლ./4860051001298 [1 l]  3.75
      bread: 1 × ბატონი ქართო დაჭრილი  1.65
      goods 5.40 + Delivery 0.99 + Service fee 2.29 + Small order fee 2.99 = 11.67  (fees and offers are computed from Glovo's published parameters, not priced by Glovo)
   w4  Wolt · Aversi Opera · open · 25-35 min · 970 m · rating 9.8
      paracetamol: 1 × პარაცეტამოლი 0.5გ #20ტ  4.26
      goods 4.26 + Small order fee 2.99 + Service fee 1.00 + Delivery (970 m) 1.55 = 9.80  (priced by Wolt)
```

Its words "about" and "priced by Wolt" say how far each total can be trusted, which the next section explains; the ratings are each platform's own, a percentage on Glovo and out of ten on Wolt.

When no store has everything, it finds the division between two stores that costs least, moving an item to the dearer shelf where that lifts a basket over a fee threshold. A list that mixes groceries with a pharmacy or household item gets a store for each kind.

## How far to trust a total

| Platform | Total is | Because |
|---|---|---|
| Wolt | exact | Wolt prices any basket for an anonymous visitor, and the tool asks it, the store's campaigns included. |
| Glovo | "about" | It is computed from the delivery price, service-fee percentage and small-basket surcharge Glovo publishes for each store. Glovo itemises a basket's fees only after sign-in, so the service fee is unchecked. |
| Bolt Food | "at least" | Bolt shows only the delivery price before sign-in. Its service, small-order and packaging fees are missing from the total, so Bolt looks cheaper than it is. |

For that reason the cheapest plan whose fees are all known, tagged "best with every fee known" as above, is always shown beside the plans that look cheaper. A store's offers that are open to every customer, such as "GEL10 off on orders over GEL60", are counted. Prices, stock and opening hours are those of the moment of the search; delivery prices in particular move through the day.

## What it does not do

- It does not order, pay, or fill a cart. You check out in the app.
- Without your account it cannot know your prices. New-customer offers and subscriber prices are listed where a platform advertises them and left out of the totals. With a subscription you pay less on that platform than shown: with Wolt+ in Georgia by up to the delivery fee and most of the service fee, while Glovo Prime and Bolt Plus publish no figures. Claude will say which way that tilts a close comparison.

## Where it works

A platform that does not deliver to your address is left out of the comparison, and the answer says so. The fee arithmetic was measured in Tbilisi. Abroad, the tool's fee figures for Wolt were checked against Wolt's own pricing in cities from Reykjavik to Almaty and agreed, but for a bag charge in one. Glovo and Bolt Food were run in other cities of Europe, Central Asia and Africa, under the same caveats as in the table above. Shelf labels differ most: where one writes a pack's size in a way the tool does not know, Claude works out how many packs you need and says that it did.

## Signing in

No account is needed for anything above. Signing in is optional and buys one thing: the Wolt baskets in Claude's answer are priced as your account pays, Wolt+ and personal offers included. On Glovo it only reads whether you hold a subscription. Bolt Food is read signed out only, because its fraud protection refuses a sign-in from this tool.

Before each request Claude asks whether to run it signed in or signed out, and says what each changes. A signed-out run asks nothing in your name, and its totals leave a membership's discount out. No cart is filled in either.

Two things to weigh first. Signing in has been tried on one real account, and worked on Wolt and on Glovo through a browser window. Pricing a basket for that account has not been tried yet. And a platform may restrict an account used this way, as the next section explains.

To sign in or out, ask Claude, which gives you a command to run in your own terminal. It opens a browser window at the platform's own sign-in page, where you sign in as usual and then close the browser; this needs Google Chrome or Chromium. What is kept is a token in a file on your computer that only you can read, and signing out deletes it.

## The platforms' terms

Shop Master reads the private web interfaces that the platforms' own sites use. Wolt's terms forbid "bots or other automated methods" and access other than through its app and website, and Bolt Food's forbid "any automated collection of data" from its platform; Glovo's terms page could not be read, so its clause is unknown here. Those clauses are from the terms for Georgia; the terms of other countries were not read. Using this tool is therefore against at least two of the three, and you use it at your own risk; signing in adds the risk that a platform restricts your account.

It asks for little. One comparison sends each platform some tens of requests, about a second apart, under an hourly ceiling of the tool's own. It waits when a platform throttles it, leaves alone one that keeps throttling, and does not retry a refusal. A signed-in account is asked far less, and is left alone at the first throttle or refusal. This restraint lowers the chance of trouble. It does not make the use one the terms allow. The interfaces can change without notice. The project is not affiliated with Wolt, Glovo or Bolt.

[skills/shop-master/platforms.md](skills/shop-master/platforms.md) records how each platform is read, how its fee rules were measured, what was found in other countries, and the limits the tool keeps to.

## Development

`python3 -m unittest discover -s tests` runs the tests, which need no network. `claude --plugin-dir .` loads the plugin from a checkout, and the tool Claude drives is a command-line program that runs by hand: `bin/shopmaster --help`.

Released under the MIT licence.
