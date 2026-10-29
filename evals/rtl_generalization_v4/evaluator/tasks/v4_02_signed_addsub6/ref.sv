module RefModule(input signed [5:0] lhs_i,input signed [5:0] rhs_i,
 input subtract_i,output reg signed [5:0] value_o,output reg clipped_o);
 reg signed [6:0] wide;
 always @* begin
   if(subtract_i) wide={lhs_i[5],lhs_i}-{rhs_i[5],rhs_i};
   else wide={lhs_i[5],lhs_i}+{rhs_i[5],rhs_i};
   clipped_o=1'b1;
   if(wide>7'sd31) value_o=6'sd31;
   else if(wide< -7'sd32) value_o=6'b100000;
   else begin value_o=wide[5:0];clipped_o=1'b0;end
 end
endmodule
