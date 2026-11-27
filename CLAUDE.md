Run the unit tests from the repository root; they need no network:

```
python3 -m unittest discover -s tests
```

To meet the plugin as a shopper would, without installing it:

```
echo "<request>" | claude -p --setting-sources project --plugin-dir . --allowedTools "Skill,Read,Bash"
```

`--setting-sources project` keeps the user's other plugins and hooks out of the test, and the request goes on stdin because `--allowedTools` takes several values and swallows a prompt placed after it. The run reads the live platforms.

The tool keeps its state under the user's home: the delivery point and the sign-in tokens in `.config/shop-master/`, the last run and the pacing record in `.cache/shop-master/`. A test that should leave those alone runs with `HOME` pointed at a scratch directory.

The pacing record is shared by every run under one home: live checks from several shells take turns at one request a second per host, and a host is refused once it has been asked as often in an hour as the tool allows, in a message that names the figure. A scratch `HOME` starts a record of its own, so live checks spread over several scratch homes add up unseen: a day of them drew `429` from Glovo for requests a second apart. Count them as one load.

A platform's fee rules are established by pricing baskets, not by reading the parameters it publishes: Wolt's published service-fee bands describe a charge its checkout does not make. The measurements behind the present rules are in `tests/test_fees.py` and `skills/shop-master/platforms.md`.
