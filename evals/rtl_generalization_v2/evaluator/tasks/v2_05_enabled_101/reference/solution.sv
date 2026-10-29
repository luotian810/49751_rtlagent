module TopModule(input clk, input reset, input en, input bit_in, output reg match);
  reg [1:0] state;
  always @(posedge clk) begin
    if(reset) begin state<=0;match<=0;end
    else begin
      match<=0;
      if(en) case(state)
        0: if(bit_in) state<=1;
        1: if(!bit_in) state<=2;
        2: if(bit_in) begin state<=1;match<=1;end else state<=0;
        default: state<=0;
      endcase
    end
  end
endmodule
