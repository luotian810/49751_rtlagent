module TopModule(input clk, input reset, input load, input en,
                 input [4:0] data, output reg [4:0] q);
  always @(posedge clk)
    if (load) q<=data;
    else if (reset) q<=5'd0;
    else if (en) q<=q+5'd1;
endmodule
