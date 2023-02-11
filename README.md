# GlobalSnapshots
Simulate the Chandy-Lamport algorithm for global snapshots using socket programming.

## Launcher

Use the launcher python script to launch the application. The terminal used to execute this script becomes the CLI for the system.

```sh
python3 launcher.py
```

### CLI Commands

For all commands, the valid client ID's can be seen from `CLIENT_PORTS` in `config.py`.

The <b>`token`</b> command generates a token at the given client and starts its circulation through the system. Note that there must only be 1 token in circulation at any time.
```
>>> token A
```

The <b>`drop`</b> command assigns a token drop probability to a client. The value can be between `0-100` and denotes the percent chance of losing the token at the specified client.
```
>>> drop B 40
```

The <b>`snapshot`</b> command requests the provided client to initiate a global snapshot.
```
>>> snapshot E
```

The <b>`simulate`</b> command will run the simulation written in `simulate.txt` file.
```
>>> simulate
```

## Simulation

The `simulate.txt` file can be edited to create an automated simulation for the system.

In addition to the CLI commands, the script can contain 2 more commands:

The `wait` command will halt sending of further commands from the CLI till the user presses enter.
```
wait
```

The `delay` command will delay the send of the next command in the simulation by the provided number of seconds. The value provided may be a float value.
```
delay 3
```

## Thoughts on TCP/UDP

Since the Chandy-Lamport algorithm for global snapshots expects communication via lossless FIFO channels, it was important for us to use TCP for connecting our clients. UDP does not guarentee a FIFO or lossless delivery of packets and therefor would not have been the right choice for our system.