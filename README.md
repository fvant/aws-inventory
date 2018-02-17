# aws-inventory
Script to find out what is deployed where in AWS

Takes a list or regions and 1 service like ec2, s3 as parameters.
```
~/aws-inventory$ ./aws-inventory.py ec2 -r eu-west-1

=== EC2 @ region 'eu-west-1' ===

name    customer    environment    state    ip    private_ip    launch_time                id
------  ----------  -------------  -------  ----  ------------  -------------------------  -------------------
                                   stopped        172.31.6.22   2018-02-05 19:02:53+00:00  i-035f05278b2a5b98f
```

If you leave out the  -r regions, it will loop over all known AWS Regions.

Based on a tool called voyeur, I hacked my requirements into it and gave it a more enterprise proxyserver friendly name.
