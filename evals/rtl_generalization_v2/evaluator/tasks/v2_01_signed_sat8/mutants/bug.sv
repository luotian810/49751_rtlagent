// Deliberate bug: overflow wraps instead of saturating.
module TopModule(input signed [7:0] a, input signed [7:0] b,
                 output signed [7:0] y, output saturated);
  assign y = a+b;
  assign saturated = 1'b0;
endmodule
