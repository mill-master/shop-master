Run the unit tests from the repository root; they need no network:

```
python3 -m unittest discover -s tests
```

To meet the plugin as a shopper would, without installing it:

```
echo "<request>" | claude -p --setting-sources project --plugin-dir . --allowedTools "Skill,Read,Bash"
```

`--setting-sources project` keeps the user's other plugins and hooks out of the test, and the request goes on stdin because `--allowedTools` takes several values and swallows a prompt placed after it. The run reads the live platforms.

The tool keeps its state under the user's home: the delivery point in `.config/shop-master/` and the last run in `.cache/shop-master/`. A test that should leave those alone runs with `HOME` pointed at a scratch directory.

A platform's fee rules are established by pricing baskets, not by reading the parameters it publishes: Wolt's published service-fee bands describe a charge its checkout does not make. The measurements behind the present rules are in `tests/test_fees.py` and `skills/shop-master/platforms.md`.
