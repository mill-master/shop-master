# Shop Master

Tells you where to order a whole shopping list for delivery in Tbilisi so that it costs least after fees.

Wolt, Glovo and Bolt Food each charge delivery, service and small-order fees per order, and no single search shows which store has everything on your list. Shop Master reads all three, prices the whole list store by store with the fees included, and names the cheapest single order or, when no store has everything, the cheapest split between two. It does the same for a restaurant dish.

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

## What it needs

Python 3 and an internet connection. No account on any platform, no API key, nothing to install.

It is built to be driven by Claude Code: the judgment of which product on a shelf is the one you meant is left to the model. Open this folder in Claude Code and ask, for example, "I need milk, eggs, bread, rice and black pepper, where should I order?". The skill in `.claude/skills/shop-master/` takes it from there. The command-line tool under it also runs by hand; `scripts/shopmaster --help` lists its commands.

Set where you want things delivered once, as coordinates:

```
.claude/skills/shop-master/scripts/shopmaster where 41.7151 44.8271 home
```

## What to know before relying on it

- It does not order, pay, or fill a cart. It prints links to the stores; you check out in the app.
- Wolt totals are exact, because Wolt prices a basket for anyone. Glovo totals are computed from the fee parameters Glovo publishes and are marked "about". Bolt Food shows only its delivery price before sign-in, so its totals are marked "at least".
- New-customer offers and Glovo Prime prices are listed where the platforms advertise them and left out of the totals. What a Wolt+ or Bolt Plus subscription changes cannot be seen without signing in.
- The platforms' web interfaces are private and can change without notice. Automated reading may be against their terms of use.

Run the tests with `python3 -m unittest discover -s tests`.
