module TopModule(input signed [7:0] a, input signed [7:0] b,
                 output reg signed [7:0] y, output reg saturated);
  reg signed [8:0] sum;
  always @* begin
    sum = {a[7], a} + {b[7], b};
    saturated = 1'b1;
    if (sum > 9'sd127) y = 8'sd127;
    else if (sum < -9'sd128) y = -8'sd128;
    else begin y = sum[7:0]; saturated = 1'b0; end
  end
endmodule
