if ps -lef | grep ssh | grep 1234
then
    echo "SSH tunnel already running"
else
    echo "Staring SSH tunnel"
    ssh -f -N -C -T -l tresobs -L1234:localhost:1234 <FLWO60_HOST>
fi
exit

