module RefModule(input signed [7:0] a, input signed [7:0] b,
                 output reg signed [7:0] y, output reg saturated);
  integer mathematical_sum;
  always @* begin
    mathematical_sum = $signed(a);
    mathematical_sum = mathematical_sum + $signed(b);
    if (mathematical_sum > 127) begin y=127; saturated=1; end
    else if (mathematical_sum < -128) begin y=-128; saturated=1; end
    else begin y=mathematical_sum; saturated=0; end
  end
endmodule
